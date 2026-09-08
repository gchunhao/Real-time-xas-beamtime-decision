from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.signal import medfilt, savgol_filter

from .registry import Profile


@dataclass(frozen=True, slots=True)
class NormalizationSelection:
    state: str
    reason: str
    selected_pre_offsets_ev: tuple[float, float] | None
    preview_pre_offsets_ev: tuple[float, float]
    diagnostics: dict[str, Any]

    @property
    def requires_review(self) -> bool:
        return self.state in {"HUMAN_LOCAL_REVIEW_REQUIRED", "REVIEW_REQUIRED"}


def _robust_sigma(values: np.ndarray, scale: float = 1.4826) -> float:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return float("nan")
    median = np.median(finite)
    return float(scale * np.median(np.abs(finite - median)))


def _odd_window(requested: int, size: int, minimum: int = 5) -> int:
    value = min(requested, size if size % 2 else size - 1)
    return value if value >= minimum else 0


def resolve_selector_state(
    wide_pre_valid: bool,
    near_pre_valid: bool,
    post_context_valid: bool,
    feature_context_valid: bool,
) -> tuple[str, str]:
    if wide_pre_valid:
        return "WIDE_PRE", "WIDE_PRE_VALID"
    if near_pre_valid:
        return "NEAR_PRE", "WIDE_PRE_INVALID__NEAR_PRE_VALID"
    if post_context_valid and feature_context_valid:
        return (
            "HUMAN_LOCAL_REVIEW_REQUIRED",
            "BOTH_PRE_WINDOWS_INVALID__POST_FEATURE_CONTEXT_USABLE",
        )
    return "REVIEW_REQUIRED", "BOTH_PRE_WINDOWS_INVALID__CONTEXT_UNUSABLE"


def _pre_diagnostics(
    energy: np.ndarray,
    signal: np.ndarray,
    e0: float,
    offsets: tuple[float, float],
    white_line_offsets: tuple[float, float],
    glitch_z: float,
) -> dict[str, Any]:
    low, high = offsets
    mask = (energy >= e0 + low) & (energy <= e0 + high)
    x = energy[mask]
    y = signal[mask]
    expected_points = max(1, int(round((high - low) / float(np.median(np.diff(energy))))) + 1)
    coverage = float(np.count_nonzero(mask)) / expected_points

    if x.size < 6:
        return {
            "coverage": coverage,
            "white_line_scale": None,
            "curvature_ratio": None,
            "extrapolation_stability": None,
            "glitch_count": None,
        }

    linear = np.polyfit(x, y, 1)
    linear_residual = y - np.polyval(linear, x)
    quadratic = np.polyfit(x, y, 2)
    quadratic_residual = y - np.polyval(quadratic, x)

    wl_mask = (
        (energy >= e0 + white_line_offsets[0])
        & (energy <= e0 + white_line_offsets[1])
    )
    white_line_scale = (
        float(np.max(signal[wl_mask]) - np.polyval(linear, e0))
        if np.count_nonzero(wl_mask) >= 3
        else float("nan")
    )

    midpoint = (low + high) / 2.0
    lower = (energy >= e0 + low) & (energy <= e0 + midpoint)
    upper = (energy >= e0 + midpoint) & (energy <= e0 + high)
    if (
        np.count_nonzero(lower) >= 3
        and np.count_nonzero(upper) >= 3
        and np.isfinite(white_line_scale)
        and abs(white_line_scale) > 0
    ):
        fit_lower = np.polyfit(energy[lower], signal[lower], 1)
        fit_upper = np.polyfit(energy[upper], signal[upper], 1)
        extrapolation_stability = float(
            abs(np.polyval(fit_lower, e0) - np.polyval(fit_upper, e0))
            / abs(white_line_scale)
        )
    else:
        extrapolation_stability = float("inf")

    median = medfilt(y, kernel_size=5 if y.size >= 5 else 3)
    residual = y - median
    sigma = _robust_sigma(residual)
    glitch_count = (
        int(np.sum(np.abs(residual) > glitch_z * sigma))
        if np.isfinite(sigma) and sigma > 0
        else 0
    )

    return {
        "coverage": coverage,
        "white_line_scale": white_line_scale,
        "curvature_ratio": float(
            _robust_sigma(linear_residual)
            / max(_robust_sigma(quadratic_residual), 1e-20)
        ),
        "extrapolation_stability": extrapolation_stability,
        "glitch_count": glitch_count,
    }


def _pre_valid(
    diagnostics: dict[str, Any],
    limits: dict[str, Any],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    coverage = diagnostics.get("coverage")
    white_line_scale = diagnostics.get("white_line_scale")
    curvature = diagnostics.get("curvature_ratio")
    extrapolation = diagnostics.get("extrapolation_stability")
    glitch_count = diagnostics.get("glitch_count")

    if coverage is None or coverage < float(limits["coverage_min"]):
        reasons.append("LOW_COVERAGE")
    if (
        white_line_scale is None
        or not np.isfinite(white_line_scale)
        or white_line_scale <= 0
    ):
        reasons.append("NONPOSITIVE_WHITE_LINE_SCALE")
    if (
        curvature is None
        or not np.isfinite(curvature)
        or curvature > float(limits["curvature_ratio_max"])
    ):
        reasons.append("CURVATURE")
    if (
        extrapolation is None
        or not np.isfinite(extrapolation)
        or extrapolation > float(limits["extrapolation_stability_max"])
    ):
        reasons.append("EXTRAPOLATION_INSTABILITY")
    if glitch_count is None or glitch_count > int(limits["glitch_count_max"]):
        reasons.append("PRE_EDGE_GLITCH")
    return not reasons, reasons


def _context_diagnostics(
    energy: np.ndarray,
    signal: np.ndarray,
    e0: float,
    pre_offsets: tuple[float, float],
    post_offsets: tuple[float, float],
    feature_offsets: tuple[float, float],
    white_line_offsets: tuple[float, float],
    feature_savgol_width: int,
    feature_savgol_order: int,
) -> tuple[dict[str, float], dict[str, float]]:
    pre_mask = (
        (energy >= e0 + pre_offsets[0])
        & (energy <= e0 + pre_offsets[1])
    )
    wl_mask = (
        (energy >= e0 + white_line_offsets[0])
        & (energy <= e0 + white_line_offsets[1])
    )
    if np.count_nonzero(pre_mask) < 3 or np.count_nonzero(wl_mask) < 3:
        return (
            {"post_norm_resid": float("inf"), "post_stability": float("inf")},
            {"feature_noise_norm": float("inf"), "feature_a_spike": float("inf")},
        )

    pre_fit = np.polyfit(energy[pre_mask], signal[pre_mask], 1)
    white_line_scale = float(np.max(signal[wl_mask]) - np.polyval(pre_fit, e0))
    if not np.isfinite(white_line_scale) or white_line_scale <= 0:
        return (
            {"post_norm_resid": float("inf"), "post_stability": float("inf")},
            {"feature_noise_norm": float("inf"), "feature_a_spike": float("inf")},
        )

    post_mask = (
        (energy >= e0 + post_offsets[0])
        & (energy <= e0 + post_offsets[1])
    )
    if np.count_nonzero(post_mask) >= 6:
        x_post = energy[post_mask]
        y_post = signal[post_mask]
        post_fit = np.polyfit(x_post, y_post, 2)
        post_norm_resid = float(
            _robust_sigma(y_post - np.polyval(post_fit, x_post))
            / abs(white_line_scale)
        )

        midpoint = (post_offsets[0] + post_offsets[1]) / 2.0
        lower = (
            (energy >= e0 + post_offsets[0])
            & (energy <= e0 + midpoint)
        )
        upper = (
            (energy >= e0 + midpoint)
            & (energy <= e0 + post_offsets[1])
        )
        if np.count_nonzero(lower) >= 4 and np.count_nonzero(upper) >= 4:
            fit_lower = np.polyfit(energy[lower], signal[lower], 2)
            fit_upper = np.polyfit(energy[upper], signal[upper], 2)
            post_stability = float(
                abs(
                    np.polyval(fit_lower, e0 + post_offsets[0])
                    - np.polyval(fit_upper, e0 + post_offsets[0])
                )
                / abs(white_line_scale)
            )
        else:
            post_stability = float("inf")
    else:
        post_norm_resid = float("inf")
        post_stability = float("inf")

    feature_mask = (
        (energy >= e0 + feature_offsets[0])
        & (energy <= e0 + feature_offsets[1])
    )
    if np.count_nonzero(feature_mask) >= 11:
        feature = signal[feature_mask]
        window = _odd_window(feature_savgol_width, feature.size)
        smooth = (
            savgol_filter(feature, window, feature_savgol_order)
            if window
            else feature
        )
        residual = feature - smooth
        sigma = _robust_sigma(residual)
        feature_noise_norm = float(sigma / abs(white_line_scale))
        feature_a_spike = (
            float(np.max(np.abs(residual)) / sigma)
            if np.isfinite(sigma) and sigma > 0
            else float("inf")
        )
    else:
        feature_noise_norm = float("inf")
        feature_a_spike = float("inf")

    return (
        {
            "post_norm_resid": post_norm_resid,
            "post_stability": post_stability,
        },
        {
            "feature_noise_norm": feature_noise_norm,
            "feature_a_spike": feature_a_spike,
        },
    )


def select_normalization(
    energy: np.ndarray,
    signal: np.ndarray,
    e0: float,
    profile: Profile,
) -> NormalizationSelection | None:
    config = profile.get("normalization.selector")
    if not config:
        return None

    wide_offsets = tuple(float(x) for x in config["wide_pre_offsets_ev"])
    near_offsets = tuple(float(x) for x in config["near_pre_offsets_ev"])
    post_offsets = tuple(float(x) for x in config["post_context"]["offsets_ev"])
    feature_offsets = tuple(float(x) for x in config["feature_context"]["offsets_ev"])
    white_line_offsets = tuple(
        float(x) for x in profile.get("quality.white_line_offsets_ev")
    )

    wide_diag = _pre_diagnostics(
        energy,
        signal,
        e0,
        wide_offsets,
        white_line_offsets,
        float(config.get("pre_glitch_z_threshold", 6.0)),
    )
    near_diag = _pre_diagnostics(
        energy,
        signal,
        e0,
        near_offsets,
        white_line_offsets,
        float(config.get("pre_glitch_z_threshold", 6.0)),
    )
    wide_valid, wide_reasons = _pre_valid(wide_diag, config["wide_limits"])
    near_valid, near_reasons = _pre_valid(near_diag, config["near_limits"])

    post_diag, feature_diag = _context_diagnostics(
        energy,
        signal,
        e0,
        near_offsets,
        post_offsets,
        feature_offsets,
        white_line_offsets,
        int(profile.get("quality.savgol.width_points", 11)),
        int(profile.get("quality.savgol.polynomial_order", 3)),
    )
    post_valid = (
        post_diag["post_norm_resid"]
        <= float(config["post_context"]["norm_resid_max"])
        and post_diag["post_stability"]
        <= float(config["post_context"]["stability_max"])
    )
    feature_valid = (
        feature_diag["feature_noise_norm"]
        <= float(config["feature_context"]["noise_norm_max"])
        and feature_diag["feature_a_spike"]
        <= float(config["feature_context"]["a_spike_max"])
    )

    state, reason = resolve_selector_state(
        wide_valid,
        near_valid,
        post_valid,
        feature_valid,
    )
    selected = (
        wide_offsets
        if state == "WIDE_PRE"
        else near_offsets
        if state == "NEAR_PRE"
        else None
    )

    return NormalizationSelection(
        state=state,
        reason=reason,
        selected_pre_offsets_ev=selected,
        preview_pre_offsets_ev=near_offsets,
        diagnostics={
            "wide_pre_valid": wide_valid,
            "wide_pre_fail_reasons": wide_reasons,
            "wide_pre": wide_diag,
            "near_pre_valid": near_valid,
            "near_pre_fail_reasons": near_reasons,
            "near_pre": near_diag,
            "post_context_valid": post_valid,
            "post_context": post_diag,
            "feature_context_valid": feature_valid,
            "feature_context": feature_diag,
            "normalization_method": "automatic_approximate",
            "normalization_precision": "screening_level",
            "manual_review_recommended_for_critical_spectra": True,
            "publication_grade_normalization": False,
            "no_quality_promotion": True,
        },
    )
