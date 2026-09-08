from __future__ import annotations

import math
from dataclasses import dataclass, field

from .models import (
    AutoExecutionEligibility,
    QualityMetrics,
    ResourceConstraint,
    RuntimeLimits,
    SampleAction,
    SchedulerAction,
    ScientificDecision,
    Spectrum,
)
from .registry import Profile


@dataclass(slots=True)
class DecisionOutcome:
    recommendation: ScientificDecision
    reason: str
    predicted_n_quant: int | None
    remaining_scan_budget: int | None
    remaining_time_seconds: float | None
    sample_action: SampleAction
    scheduler_action: SchedulerAction
    auto_execution_eligibility: AutoExecutionEligibility
    resource_constraint: ResourceConstraint
    effective_scheduler_action: SchedulerAction
    reason_codes: list[str] = field(default_factory=list)
    suggested_reviewer_action: str | None = None
    confidence: str = "MODERATE"
    alpha_global: float | None = None
    alpha_recent: float | None = None
    alpha_pred: float | None = None


class DecisionEngine:
    """ADP v1.0 shadow orchestration.

    Frozen P_K_XANES v1.2 determines whether the objective route is reached.
    This class keeps the scientific decision separate from beamtime/resource
    constraints and never requires reviewer approval for ordinary STOP/CONTINUE.
    """

    policy_version = "ADP_v1.0-shadow"
    def __init__(self, profile: Profile):
        self.profile = profile

    def decide(
        self,
        metrics: QualityMetrics,
        scan_count: int,
        total_seconds: float,
        scans: list[Spectrum],
        limits: RuntimeLimits,
        prior_metrics: list[QualityMetrics] | None = None,
    ) -> DecisionOutcome:
        remaining_scans, remaining_time, resource_constraint, effective_remaining = self._resources(
            scan_count, total_seconds, scans, limits
        )
        alpha_global, alpha_recent, alpha_pred = self._estimate_alpha(prior_metrics or [], metrics)
        predicted = self._predict_fastest(metrics, scan_count, alpha_pred)

        if metrics.route in {"A", "B"}:
            profile_label = self.profile.id
            return DecisionOutcome(
                recommendation=ScientificDecision.STOP,
                reason=f"{profile_label} Route {metrics.route} target reached",
                predicted_n_quant=scan_count,
                remaining_scan_budget=remaining_scans,
                remaining_time_seconds=remaining_time,
                sample_action=SampleAction.FINISH_SAMPLE,
                scheduler_action=SchedulerAction.ADVANCE_TO_NEXT_SAMPLE,
                auto_execution_eligibility=AutoExecutionEligibility.ELIGIBLE,
                resource_constraint=resource_constraint,
                effective_scheduler_action=SchedulerAction.ADVANCE_TO_NEXT_SAMPLE,
                reason_codes=[self._target_reason_code("TARGET_ATTAINED")],
                confidence="HIGH",
                alpha_global=alpha_global,
                alpha_recent=alpha_recent,
                alpha_pred=alpha_pred,
            )

        reason_codes: list[str] = [self._target_reason_code("TARGET_NOT_REACHED")]
        if metrics.e0 is None:
            reason = "Continue: E0 or required windows are not yet evaluable"
            reason_codes.append("E0_NOT_EVALUABLE")
        elif predicted is None and scan_count >= 2:
            reason = "Continue one scan and reassess: averaging benefit cannot be projected safely"
            reason_codes.append("PREDICTION_UNSUPPORTED_REASSESS_ONE")
        elif predicted is not None and effective_remaining is not None and predicted > scan_count + effective_remaining:
            reason = "Scientific target not reached; available resource budget is insufficient for the current forecast"
            reason_codes.append("FORECAST_EXCEEDS_RESOURCE_BUDGET")
        else:
            reason = f"Continue: {self.profile.id} quantitative target has not yet been reached"

        if predicted is None and scan_count >= 2:
            confidence = "LOW"
        elif scan_count == 1:
            confidence = "MODERATE"
        else:
            confidence = "MODERATE"

        effective_scheduler = SchedulerAction.STAY_ON_SAMPLE
        auto_eligibility = AutoExecutionEligibility.ELIGIBLE
        if resource_constraint is not ResourceConstraint.NONE and effective_remaining == 0:
            effective_scheduler = SchedulerAction.ADVANCE_TO_NEXT_SAMPLE
            auto_eligibility = AutoExecutionEligibility.BLOCKED
            reason_codes.append(resource_constraint.value)

        return DecisionOutcome(
            recommendation=ScientificDecision.CONTINUE,
            reason=reason,
            predicted_n_quant=predicted,
            remaining_scan_budget=remaining_scans,
            remaining_time_seconds=remaining_time,
            sample_action=SampleAction.ACQUIRE_MORE,
            scheduler_action=SchedulerAction.STAY_ON_SAMPLE,
            auto_execution_eligibility=auto_eligibility,
            resource_constraint=resource_constraint,
            effective_scheduler_action=effective_scheduler,
            reason_codes=reason_codes,
            confidence=confidence,
            alpha_global=alpha_global,
            alpha_recent=alpha_recent,
            alpha_pred=alpha_pred,
        )

    def review_required(
        self,
        reason: str,
        reason_codes: list[str],
        remaining_scan_budget: int | None = None,
        remaining_time_seconds: float | None = None,
        suggested_reviewer_action: str = "MANUAL_ASSESSMENT",
    ) -> DecisionOutcome:
        return DecisionOutcome(
            recommendation=ScientificDecision.REVIEW_REQUIRED,
            reason=reason,
            predicted_n_quant=None,
            remaining_scan_budget=remaining_scan_budget,
            remaining_time_seconds=remaining_time_seconds,
            sample_action=SampleAction.HOLD_FOR_REVIEW,
            scheduler_action=SchedulerAction.ADVANCE_TO_NEXT_SAMPLE,
            auto_execution_eligibility=AutoExecutionEligibility.BLOCKED,
            resource_constraint=ResourceConstraint.NONE,
            effective_scheduler_action=SchedulerAction.ADVANCE_TO_NEXT_SAMPLE,
            reason_codes=reason_codes,
            suggested_reviewer_action=suggested_reviewer_action,
            confidence="HIGH",
        )

    def reacquire(
        self,
        reason: str,
        reason_codes: list[str],
        remaining_scan_budget: int | None = None,
        remaining_time_seconds: float | None = None,
    ) -> DecisionOutcome:
        return DecisionOutcome(
            recommendation=ScientificDecision.REACQUIRE,
            reason=reason,
            predicted_n_quant=None,
            remaining_scan_budget=remaining_scan_budget,
            remaining_time_seconds=remaining_time_seconds,
            sample_action=SampleAction.REACQUIRE_SCAN,
            scheduler_action=SchedulerAction.STAY_ON_SAMPLE,
            auto_execution_eligibility=AutoExecutionEligibility.ELIGIBLE,
            resource_constraint=ResourceConstraint.NONE,
            effective_scheduler_action=SchedulerAction.STAY_ON_SAMPLE,
            reason_codes=reason_codes,
            confidence="HIGH",
        )

    def _resources(
        self,
        scan_count: int,
        total_seconds: float,
        scans: list[Spectrum],
        limits: RuntimeLimits,
    ) -> tuple[int | None, float | None, ResourceConstraint, int | None]:
        remaining_scans = None if limits.maximum_scans is None else max(limits.maximum_scans - scan_count, 0)
        remaining_time = None if limits.maximum_time_seconds is None else max(limits.maximum_time_seconds - total_seconds, 0.0)
        measured = [float(s.metadata.duration_seconds) for s in scans if s.metadata.duration_seconds and s.metadata.duration_seconds > 0]
        actual_mean_duration = sum(measured) / len(measured) if measured else None
        time_scan_budget = None
        if remaining_time is not None and actual_mean_duration:
            time_scan_budget = max(math.floor(remaining_time / actual_mean_duration), 0)
        effective_remaining = self._minimum_known(remaining_scans, time_scan_budget)
        scan_exhausted = remaining_scans == 0 if remaining_scans is not None else False
        time_exhausted = time_scan_budget == 0 if time_scan_budget is not None else False
        if scan_exhausted and time_exhausted:
            constraint = ResourceConstraint.SCAN_AND_TIME_LIMIT_EXHAUSTED
        elif scan_exhausted:
            constraint = ResourceConstraint.SCAN_LIMIT_EXHAUSTED
        elif time_exhausted:
            constraint = ResourceConstraint.TIME_LIMIT_EXHAUSTED
        else:
            constraint = ResourceConstraint.NONE
        return remaining_scans, remaining_time, constraint, effective_remaining

    def _target_reason_code(self, suffix: str) -> str:
        version = str(self.profile.data.get("version") or "").replace(".", "")
        prefix = f"V{version}" if version else "PROFILE"
        return f"{prefix}_{suffix}"

    @staticmethod
    def _minimum_known(a: int | None, b: int | None) -> int | None:
        known = [value for value in (a, b) if value is not None]
        return min(known) if known else None

    def _predict_fastest(self, metrics: QualityMetrics, scan_count: int, alpha_pred: float | None) -> int | None:
        if metrics.q_hf is None or metrics.q_hf <= 0:
            return None
        alpha = 0.5 if scan_count == 1 else alpha_pred
        if alpha is None or alpha <= 0:
            return None
        alpha = min(float(alpha), 0.5)
        candidates: list[int] = []
        route_a_target = float(self.profile.get("quality.route_a.q_hf_max"))
        candidates.append(self._required(scan_count, metrics.q_hf / route_a_target, alpha))
        route_b = self.profile.get("quality.route_b")
        ratios = [metrics.q_hf / float(route_b["q_hf_max"])]
        ratios.append(metrics.q_pre / float(route_b["q_pre_max"]) if metrics.q_pre is not None else float("inf"))
        ratios.append(metrics.q_post / float(route_b["q_post_max"]) if metrics.q_post is not None else float("inf"))
        if metrics.a_spike is not None and metrics.a_spike <= float(route_b["a_spike_max"]):
            candidates.append(self._required(scan_count, max(ratios), alpha))
        # Return the mathematical total-scan forecast without an arbitrary
        # hard cutoff. Validation range/confidence is a separate ADP concern
        # and must not truncate the frozen Route A/Route B calculation.
        return min(candidates) if candidates else None

    @staticmethod
    def _required(scan_count: int, ratio: float, alpha: float) -> int:
        if not math.isfinite(ratio):
            return 2**31 - 1
        return max(scan_count, int(math.ceil(scan_count * max(ratio, 1.0) ** (1.0 / alpha))))

    @staticmethod
    def _estimate_alpha(
        prior_metrics: list[QualityMetrics], current: QualityMetrics
    ) -> tuple[float | None, float | None, float | None]:
        series = [m.q_hf for m in prior_metrics] + [current.q_hf]
        if len(series) < 2 or any(value is None or value <= 0 for value in series):
            return None, None, None
        values = [float(value) for value in series if value is not None]
        ns = list(range(1, len(values) + 1))
        slopes: list[float] = []
        for i in range(len(values)):
            for j in range(i + 1, len(values)):
                denominator = math.log(ns[j]) - math.log(ns[i])
                if denominator:
                    slopes.append(-(math.log(values[j]) - math.log(values[i])) / denominator)
        alpha_global = sorted(slopes)[len(slopes) // 2] if slopes else None
        alpha_recent = -math.log(values[-1] / values[-2]) / math.log(ns[-1] / ns[-2])
        positive = [value for value in (alpha_global, alpha_recent, 0.5) if value is not None and value > 0]
        alpha_pred = min(positive) if len(positive) == 3 else None
        if alpha_pred is not None:
            alpha_pred = min(alpha_pred, 0.5)
        return alpha_global, alpha_recent, alpha_pred
