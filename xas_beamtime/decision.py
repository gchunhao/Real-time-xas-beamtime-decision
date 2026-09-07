from __future__ import annotations

import math
from dataclasses import dataclass

from .models import QualityMetrics, Recommendation, RuntimeLimits, Spectrum
from .registry import Profile


@dataclass(slots=True)
class DecisionOutcome:
    recommendation: Recommendation
    reason: str
    predicted_n_quant: int | None
    remaining_scan_budget: int | None
    remaining_time_seconds: float | None


class DecisionEngine:
    """Advisory state machine. It intentionally has no acquisition-control action."""

    def __init__(self, profile: Profile):
        self.profile = profile

    def decide(
        self,
        metrics: QualityMetrics,
        scan_count: int,
        total_seconds: float,
        scans: list[Spectrum],
        limits: RuntimeLimits,
    ) -> DecisionOutcome:
        remaining_scans = None if limits.maximum_scans is None else max(limits.maximum_scans - scan_count, 0)
        remaining_time = None if limits.maximum_time_seconds is None else max(limits.maximum_time_seconds - total_seconds, 0.0)
        measured = [float(s.metadata.duration_seconds) for s in scans if s.metadata.duration_seconds and s.metadata.duration_seconds > 0]
        actual_mean_duration = sum(measured) / len(measured) if measured else None
        time_scan_budget = None
        if remaining_time is not None and actual_mean_duration:
            time_scan_budget = max(math.floor(remaining_time / actual_mean_duration), 0)
        effective_remaining = self._minimum_known(remaining_scans, time_scan_budget)
        predicted = self._predict_fastest(metrics, scan_count)
        if metrics.route in {"A", "B"}:
            return DecisionOutcome(
                Recommendation.STOP_RECOMMENDED,
                f"{metrics.route} quantitative route reached; human confirmation is required",
                scan_count,
                remaining_scans,
                remaining_time,
            )
        exhausted = effective_remaining == 0
        if exhausted and metrics.usable_protected_region:
            return DecisionOutcome(
                Recommendation.QL_ONLY,
                "Quantitative route not reached within the strictest active limit; protected XANES region remains qualitatively usable",
                predicted,
                remaining_scans,
                remaining_time,
            )
        if exhausted:
            return DecisionOutcome(
                Recommendation.STOP_RECOMMENDED,
                "Strictest active limit reached and the protected XANES region is below qualitative readiness",
                predicted,
                remaining_scans,
                remaining_time,
            )
        if metrics.e0 is None:
            reason = "Continue: E0 or required windows are not yet evaluable"
        elif predicted is not None and effective_remaining is not None and predicted > scan_count + effective_remaining:
            reason = "Continue while budget remains; quantitative readiness is not projected within the strictest active limit"
        else:
            reason = "Continue: quantitative route has not yet been reached"
        return DecisionOutcome(Recommendation.CONTINUE, reason, predicted, remaining_scans, remaining_time)

    @staticmethod
    def _minimum_known(a: int | None, b: int | None) -> int | None:
        known = [value for value in (a, b) if value is not None]
        return min(known) if known else None

    def _predict_fastest(self, metrics: QualityMetrics, scan_count: int) -> int | None:
        if metrics.q_hf is None or metrics.q_hf <= 0:
            return None
        alpha = float(self.profile.get("averaging.initial_alpha", 0.50))
        candidates: list[int] = []
        route_a_target = float(self.profile.get("quality.route_a.q_hf_max"))
        candidates.append(self._required(scan_count, metrics.q_hf / route_a_target, alpha))
        route_b = self.profile.get("quality.route_b")
        ratios = [metrics.q_hf / float(route_b["q_hf_max"])]
        if metrics.q_pre is not None:
            ratios.append(metrics.q_pre / float(route_b["q_pre_max"]))
        else:
            ratios.append(float("inf"))
        if metrics.q_post is not None:
            ratios.append(metrics.q_post / float(route_b["q_post_max"]))
        else:
            ratios.append(float("inf"))
        if metrics.a_spike is not None and metrics.a_spike <= float(route_b["a_spike_max"]):
            candidates.append(self._required(scan_count, max(ratios), alpha))
        return min(candidates) if candidates else None

    @staticmethod
    def _required(scan_count: int, ratio: float, alpha: float) -> int:
        if not math.isfinite(ratio):
            return 2**31 - 1
        return max(scan_count, int(math.ceil(scan_count * max(ratio, 1.0) ** (1.0 / alpha))))
