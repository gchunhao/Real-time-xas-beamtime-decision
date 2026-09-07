from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Recommendation(str, Enum):
    CONTINUE = "CONTINUE"
    QL_ONLY = "QL ONLY"
    STOP_RECOMMENDED = "STOP RECOMMENDED"


@dataclass(slots=True)
class ScanMetadata:
    source_path: str
    element: str | None = None
    edge: str | None = None
    scan_type: str | None = None
    sample_id: str | None = None
    scan_number: int | None = None
    duration_seconds: float | None = None
    started_at: str | None = None
    beamline: str | None = None
    parser_name: str = "text_table"
    parser_version: str = "0.1"
    header: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Spectrum:
    energy: np.ndarray
    mu: np.ndarray
    metadata: ScanMetadata
    raw_columns: dict[str, np.ndarray] = field(default_factory=dict)


@dataclass(slots=True)
class Region:
    name: str
    start: float
    end: float
    protected: bool


@dataclass(slots=True)
class Anomaly:
    energy: float
    magnitude: float
    region: str
    protected: bool
    automatically_masked: bool
    status: str = "unreviewed"


@dataclass(slots=True)
class QualityMetrics:
    q_hf: float | None
    q_pre: float | None
    q_post: float | None
    a_spike: float | None
    e0: float | None
    white_line_scale: float | None
    normalization_mode: str
    route: str | None
    usable_protected_region: bool
    diagnostics: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AnalysisResult:
    analysis_id: str
    sample_id: str
    profile_id: str
    scan_count: int
    scan_ids: list[str]
    energy: np.ndarray
    raw_average: np.ndarray
    normalized_average: np.ndarray
    metrics: QualityMetrics
    regions: list[Region]
    anomalies: list[Anomaly]
    recommendation: Recommendation
    recommendation_reason: str
    marginal_gain: float | None
    predicted_n_quant: int | None
    n_quant: int | None
    total_measured_seconds: float
    remaining_scan_budget: int | None
    remaining_time_seconds: float | None
    averaging_mode: str
    uncertainty: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, include_arrays: bool = True) -> dict[str, Any]:
        result = asdict(self)
        result["recommendation"] = self.recommendation.value
        if include_arrays:
            result["energy"] = self.energy.tolist()
            result["raw_average"] = self.raw_average.tolist()
            result["normalized_average"] = self.normalized_average.tolist()
        else:
            result.pop("energy", None)
            result.pop("raw_average", None)
            result.pop("normalized_average", None)
        return result


@dataclass(slots=True)
class RuntimeLimits:
    maximum_scans: int | None = None
    maximum_time_seconds: float | None = None


@dataclass(slots=True)
class HumanFeedback:
    analysis_id: str
    sample_id: str
    profile_id: str
    rating: str
    override_recommendation: str | None
    averaging_mode: str
    included_scans: list[str]
    excluded_scans: list[str]
    glitch_decisions: list[dict[str, Any]]
    local_normalization_anchors: dict[str, list[float]]
    notes: str = ""
    reviewer_role: str = "beamline_user"
    created_at: str = field(default_factory=utc_now)


def canonical_scan_id(metadata: ScanMetadata) -> str:
    sample = metadata.sample_id or Path(metadata.source_path).stem
    number = metadata.scan_number if metadata.scan_number is not None else 0
    return f"{sample}:scan-{number}"
