from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import asdict
from typing import Iterable

import numpy as np
from scipy.signal import medfilt, savgol_filter

from .models import (
    AnalysisResult,
    Anomaly,
    QualityMetrics,
    Region,
    RuntimeLimits,
    Spectrum,
    canonical_scan_id,
)
from .registry import Profile


def robust_sigma(values: np.ndarray, scale: float = 1.4826) -> float:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return float("nan")
    median = np.median(finite)
    return float(scale * np.median(np.abs(finite - median)))


def _odd_window(requested: int, size: int, minimum: int = 5) -> int:
    value = min(requested, size if size % 2 else size - 1)
    return value if value >= minimum else 0


class AnalysisEngine:
    algorithm_version = "xas-analysis-0.1.0"

    def analyze_series(
        self,
        scans: Iterable[Spectrum],
        profile: Profile,
        limits: RuntimeLimits,
        averaging_mode: str = "equal",
        included_scan_ids: set[str] | None = None,
        anchors: dict[str, list[float]] | None = None,
    ) -> list[AnalysisResult]:
        ordered = sorted(
            scans,
            key=lambda s: (
                s.metadata.scan_number is None,
                s.metadata.scan_number or 0,
                s.metadata.source_path,
            ),
        )
        if included_scan_ids is not None:
            ordered = [s for s in ordered if canonical_scan_id(s.metadata) in included_scan_ids]
        results: list[AnalysisResult] = []
        for count in range(1, len(ordered) + 1):
            current = self._analyze(
                ordered[:count], profile, limits, averaging_mode, anchors,
                prior_metrics=[result.metrics for result in results],
            )
            if results:
                previous = results[-1].metrics.q_hf
                current_value = current.metrics.q_hf
                if previous and current_value is not None:
                    current.marginal_gain = (previous - current_value) / previous
            results.append(current)
        first_quant = next((r.scan_count for r in results if r.metrics.route in {"A", "B"}), None)
        for result in results:
            result.n_quant = first_quant
        return results

    def _analyze(
        self,
        scans: list[Spectrum],
        profile: Profile,
        limits: RuntimeLimits,
        averaging_mode: str,
        anchors: dict[str, list[float]] | None,
        prior_metrics: list[QualityMetrics] | None = None,
    ) -> AnalysisResult:
        energy, aligned = self._align(scans, float(profile.get("energy.interpolation_step_ev", 0.15)))
        e0_seed = self._find_e0(energy, np.nanmean(aligned, axis=0), profile)
        regions = self._regions(e0_seed, profile) if e0_seed is not None else []
        cleaned, anomalies = self._detect_and_mask(energy, aligned, regions, profile)
        weights = self._weights(energy, cleaned, e0_seed, profile, averaging_mode)
        raw_average = np.average(cleaned, axis=0, weights=weights)
        metrics, normalized = self._metrics(energy, raw_average, profile, anchors)
        uncertainty = self._uncertainty(energy, cleaned, profile, anchors, metrics.q_hf)
        total_seconds = sum(float(scan.metadata.duration_seconds or 0.0) for scan in scans)
        scan_ids = [canonical_scan_id(scan.metadata) for scan in scans]
        from .decision import DecisionEngine

        outcome = DecisionEngine(profile).decide(
            metrics, len(scans), total_seconds, scans, limits, prior_metrics=prior_metrics
        )
        source_fingerprints = [self._fingerprint(scan) for scan in scans]
        return AnalysisResult(
            analysis_id=str(uuid.uuid4()),
            sample_id=scans[0].metadata.logical_sample_key or scans[0].metadata.sample_id or "unknown",
            profile_id=profile.id,
            scan_count=len(scans),
            scan_ids=scan_ids,
            energy=energy,
            raw_average=raw_average,
            normalized_average=normalized,
            metrics=metrics,
            regions=regions,
            anomalies=anomalies,
            recommendation=outcome.recommendation,
            recommendation_reason=outcome.reason,
            marginal_gain=None,
            predicted_n_quant=outcome.predicted_n_quant,
            n_quant=None,
            total_measured_seconds=total_seconds,
            remaining_scan_budget=outcome.remaining_scan_budget,
            remaining_time_seconds=outcome.remaining_time_seconds,
            averaging_mode=averaging_mode,
            physical_scan_count=len(scans),
            usable_scan_count=len(scans),
            sample_action=outcome.sample_action,
            scheduler_action=outcome.scheduler_action,
            auto_execution_eligibility=outcome.auto_execution_eligibility,
            resource_constraint=outcome.resource_constraint,
            effective_scheduler_action=outcome.effective_scheduler_action,
            decision_reason_codes=outcome.reason_codes,
            suggested_reviewer_action=outcome.suggested_reviewer_action,
            decision_confidence=outcome.confidence,
            decision_policy_version=DecisionEngine.policy_version,
            uncertainty={
                **uncertainty,
                "alpha_global": outcome.alpha_global,
                "alpha_recent": outcome.alpha_recent,
                "alpha_pred": outcome.alpha_pred,
            },
            provenance={
                "algorithm_version": self.algorithm_version,
                "profile_version": profile.data.get("version"),
                "profile_sha256": hashlib.sha256(profile.source.read_bytes()).hexdigest(),
                "source_fingerprints": source_fingerprints,
                "protected_anomalies_auto_removed": False,
                "actual_duration_used": True,
            },
        )

    def _uncertainty(
        self,
        energy: np.ndarray,
        aligned: np.ndarray,
        profile: Profile,
        anchors: dict[str, list[float]] | None,
        observed_q_hf: float | None,
    ) -> dict[str, object]:
        alpha = float(profile.get("averaging.initial_alpha", 0.50))
        base: dict[str, object] = {
            "n_quant_model": "Q(N) = Q(current) * (current/N)^alpha",
            "alpha": alpha,
            "prediction_is_confirmed": False,
        }
        if aligned.shape[0] < 2 or observed_q_hf is None:
            return {**base, "q_hf_interval_95": None, "method": "unavailable_for_single_scan"}
        rng = np.random.default_rng(12012)
        values: list[float] = []
        for _ in range(100):
            indices = rng.integers(0, aligned.shape[0], aligned.shape[0])
            average = np.mean(aligned[indices], axis=0)
            metrics, _ = self._metrics(energy, average, profile, anchors)
            if metrics.q_hf is not None and np.isfinite(metrics.q_hf):
                values.append(metrics.q_hf)
        if len(values) < 20:
            return {**base, "q_hf_interval_95": None, "method": "bootstrap_insufficient"}
        return {
            **base,
            "q_hf_interval_95": [float(np.quantile(values, .025)), float(np.quantile(values, .975))],
            "method": "deterministic_scan_bootstrap",
            "replicates": 100,
        }

    @staticmethod
    def _fingerprint(scan: Spectrum) -> dict[str, str]:
        payload = np.column_stack([scan.energy, scan.mu]).tobytes()
        return {"path": scan.metadata.source_path, "sha256": hashlib.sha256(payload).hexdigest()}

    @staticmethod
    def _align(scans: list[Spectrum], step: float) -> tuple[np.ndarray, np.ndarray]:
        start = max(float(np.min(scan.energy)) for scan in scans)
        end = min(float(np.max(scan.energy)) for scan in scans)
        if end <= start:
            raise ValueError("Scans have no overlapping energy range")
        energy = np.arange(math.ceil(start / step) * step, end + step * 0.1, step)
        aligned = np.vstack([np.interp(energy, scan.energy, scan.mu) for scan in scans])
        return energy, aligned

    @staticmethod
    def _find_e0(energy: np.ndarray, signal: np.ndarray, profile: Profile) -> float | None:
        low, high = profile.get("energy.edge_search_window_ev")
        mask = (energy >= low) & (energy <= high)
        if np.count_nonzero(mask) < 7:
            return None
        local = signal[mask]
        window = _odd_window(11, local.size)
        smooth = savgol_filter(local, window, 3) if window else local
        derivative = np.gradient(smooth, energy[mask])
        return float(energy[mask][int(np.nanargmax(derivative))])

    @staticmethod
    def _regions(e0: float, profile: Profile) -> list[Region]:
        config = profile.get("quality.anomaly_detection", {})
        result: list[Region] = []
        for item in config.get("protected_regions", []):
            result.append(Region(item["name"], e0 + item["offsets_ev"][0], e0 + item["offsets_ev"][1], True))
        for item in config.get("safe_regions", []):
            result.append(Region(item["name"], e0 + item["offsets_ev"][0], e0 + item["offsets_ev"][1], False))
        return result

    @staticmethod
    def _detect_and_mask(
        energy: np.ndarray,
        aligned: np.ndarray,
        regions: list[Region],
        profile: Profile,
    ) -> tuple[np.ndarray, list[Anomaly]]:
        cleaned = aligned.copy()
        anomalies: list[Anomaly] = []
        safe_z = float(profile.get("quality.anomaly_detection.safe_zone_z_threshold", 6.0))
        protected_z = float(profile.get("quality.anomaly_detection.protected_zone_z_threshold", 4.5))
        for row_index, row in enumerate(aligned):
            window = _odd_window(9, row.size)
            smooth = medfilt(row, kernel_size=window) if window else row
            residual = row - smooth
            for region in regions:
                mask = (energy >= region.start) & (energy <= region.end)
                local = residual[mask]
                sigma = robust_sigma(local)
                if np.isfinite(sigma) and sigma <= 0:
                    nonzero = np.abs(local[np.abs(local) > np.finfo(float).eps * 32])
                    sigma = float(1.4826 * np.median(nonzero)) if nonzero.size else float("nan")
                if not np.isfinite(sigma) or sigma <= 0:
                    continue
                threshold = (protected_z if region.protected else safe_z) * sigma
                indices = np.flatnonzero(mask & (np.abs(residual) > threshold))
                for index in indices:
                    automatically_masked = not region.protected
                    anomalies.append(
                        Anomaly(
                            energy=float(energy[index]),
                            magnitude=float(residual[index]),
                            region=region.name,
                            protected=region.protected,
                            automatically_masked=automatically_masked,
                        )
                    )
                    if automatically_masked and 0 < index < len(row) - 1:
                        cleaned[row_index, index] = (cleaned[row_index, index - 1] + cleaned[row_index, index + 1]) / 2
        return cleaned, anomalies

    @staticmethod
    def _weights(
        energy: np.ndarray,
        aligned: np.ndarray,
        e0: float | None,
        profile: Profile,
        averaging_mode: str,
    ) -> np.ndarray:
        if averaging_mode != "noise_weighted" or e0 is None:
            return np.ones(aligned.shape[0])
        offsets = profile.get("normalization.pre_edge_offsets_ev")
        mask = (energy >= e0 + offsets[0]) & (energy <= e0 + offsets[1])
        weights = []
        for row in aligned:
            if np.count_nonzero(mask) < 3:
                weights.append(1.0)
                continue
            fit = np.polyfit(energy[mask], row[mask], 1)
            sigma = robust_sigma(row[mask] - np.polyval(fit, energy[mask]))
            weights.append(1.0 / max(sigma * sigma, 1e-20))
        result = np.asarray(weights)
        return result / np.sum(result)

    def _metrics(
        self,
        energy: np.ndarray,
        signal: np.ndarray,
        profile: Profile,
        anchors: dict[str, list[float]] | None,
    ) -> tuple[QualityMetrics, np.ndarray]:
        diagnostics: list[str] = []
        e0 = self._find_e0(energy, signal, profile)
        if e0 is None:
            metrics = QualityMetrics(None, None, None, None, None, None, "unavailable", None, False, ["E0 not found"])
            return metrics, np.full_like(signal, np.nan)
        pre_offsets = (anchors or {}).get("pre", profile.get("normalization.pre_edge_offsets_ev"))
        post_offsets = (anchors or {}).get("post", profile.get("normalization.post_edge_offsets_ev"))
        pre_mask = (energy >= e0 + pre_offsets[0]) & (energy <= e0 + pre_offsets[1])
        post_mask = (energy >= e0 + post_offsets[0]) & (energy <= e0 + post_offsets[1])
        feature_offsets = profile.get("quality.feature_offsets_ev")
        feature_mask = (energy >= e0 + feature_offsets[0]) & (energy <= e0 + feature_offsets[1])
        wl_offsets = profile.get("quality.white_line_offsets_ev")
        wl_mask = (energy >= e0 + wl_offsets[0]) & (energy <= e0 + wl_offsets[1])
        if np.count_nonzero(pre_mask) < 3 or np.count_nonzero(wl_mask) < 3:
            metrics = QualityMetrics(None, None, None, None, e0, None, "unavailable", None, False, ["Insufficient pre-edge or white-line coverage"])
            return metrics, np.full_like(signal, np.nan)
        pre_fit = np.polyfit(energy[pre_mask], signal[pre_mask], 1)
        baseline = np.polyval(pre_fit, energy)
        white_line_scale = float(np.max(signal[wl_mask]) - np.polyval(pre_fit, e0))
        if not np.isfinite(white_line_scale) or white_line_scale <= 0:
            metrics = QualityMetrics(None, None, None, None, e0, white_line_scale, "unavailable", None, False, ["Non-positive white-line scale"])
            return metrics, np.full_like(signal, np.nan)
        scale = float(profile.get("quality.robust_mad_scale", 1.4826))
        q_pre = robust_sigma(signal[pre_mask] - np.polyval(pre_fit, energy[pre_mask]), scale) / white_line_scale
        q_post: float | None = None
        if np.count_nonzero(post_mask) >= 5:
            post_fit = np.polyfit(energy[post_mask], signal[post_mask], 2)
            q_post = robust_sigma(signal[post_mask] - np.polyval(post_fit, energy[post_mask]), scale) / white_line_scale
        else:
            diagnostics.append("Post-edge coverage is insufficient; local normalization used")
        if np.count_nonzero(feature_mask) < 11:
            metrics = QualityMetrics(None, q_pre, q_post, None, e0, white_line_scale, "local", None, False, diagnostics + ["Protected feature region incomplete"])
            return metrics, (signal - baseline) / white_line_scale
        feature = signal[feature_mask]
        window = _odd_window(int(profile.get("quality.savgol.width_points", 11)), feature.size)
        smooth = savgol_filter(feature, window, int(profile.get("quality.savgol.polynomial_order", 3)))
        residual = feature - smooth
        robust_feature = robust_sigma(residual, scale)
        q_hf = robust_feature / white_line_scale
        a_spike = float(np.max(np.abs(residual)) / robust_feature) if robust_feature > 0 else float("inf")
        route: str | None = None
        if q_hf <= float(profile.get("quality.route_a.q_hf_max")):
            route = "A"
        route_b = profile.get("quality.route_b")
        if route is None and all(
            [
                q_hf <= float(route_b["q_hf_max"]),
                q_pre <= float(route_b["q_pre_max"]),
                q_post is not None and q_post <= float(route_b["q_post_max"]),
                a_spike <= float(route_b["a_spike_max"]),
            ]
        ):
            route = "B"
        qualitative = profile.get("quality.qualitative_guardrails")
        usable = q_hf <= float(qualitative["q_hf_max"]) and a_spike <= float(qualitative["a_spike_max"])
        normalization_mode = "full" if q_post is not None else "local"
        if normalization_mode == "local":
            diagnostics.append("Quantitative metrics use local pre-edge baseline and white-line scale")
        metrics = QualityMetrics(q_hf, q_pre, q_post, a_spike, e0, white_line_scale, normalization_mode, route, usable, diagnostics)
        return metrics, (signal - baseline) / white_line_scale
