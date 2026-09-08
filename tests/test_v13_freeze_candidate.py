from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from xas_beamtime.analysis import AnalysisEngine
from xas_beamtime.decision import DecisionEngine
from xas_beamtime.models import QualityMetrics, RuntimeLimits, ScanMetadata, Spectrum
from xas_beamtime.normalization_selector import (
    NormalizationSelection,
    resolve_selector_state,
)
from xas_beamtime.registry import ProfileRegistry


class V13FreezeCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        registry = ProfileRegistry()
        self.v12 = registry.get("P_K_XANES_v1.2")
        self.v13 = registry.get("P_K_XANES_v1.3")

    def test_candidate_profile_preserves_route_thresholds(self) -> None:
        self.assertEqual(self.v13.get("status"), "freeze-candidate")
        self.assertEqual(
            self.v13.get("energy.edge_search_window_ev"),
            [2147.5, 2152.9],
        )
        self.assertEqual(
            self.v13.get("normalization.selector.wide_pre_offsets_ev"),
            [-20.0, -10.0],
        )
        self.assertEqual(
            self.v13.get("normalization.selector.near_pre_offsets_ev"),
            [-10.0, -5.0],
        )
        for key in (
            "quality.route_a.q_hf_max",
            "quality.route_b.q_hf_max",
            "quality.route_b.q_pre_max",
            "quality.route_b.q_post_max",
            "quality.route_b.a_spike_max",
        ):
            self.assertEqual(self.v13.get(key), self.v12.get(key))

    def test_four_state_resolution(self) -> None:
        self.assertEqual(
            resolve_selector_state(True, False, False, False)[0],
            "WIDE_PRE",
        )
        self.assertEqual(
            resolve_selector_state(False, True, False, False)[0],
            "NEAR_PRE",
        )
        self.assertEqual(
            resolve_selector_state(False, False, True, True)[0],
            "HUMAN_LOCAL_REVIEW_REQUIRED",
        )
        self.assertEqual(
            resolve_selector_state(False, False, False, True)[0],
            "REVIEW_REQUIRED",
        )

    def test_review_state_enforces_no_quality_promotion(self) -> None:
        energy = np.arange(2125.0, 2210.0, 0.15)
        signal = (
            0.0005 * (energy - 2125.0)
            + 1.0 / (1.0 + np.exp(-(energy - 2151.5) / 0.6))
        )
        scan = Spectrum(
            energy,
            signal,
            ScanMetadata(
                "synthetic-v13.dat",
                element="P",
                edge="K",
                scan_type="XANES",
                sample_id="synthetic-v13",
                scan_number=1,
                duration_seconds=60.0,
            ),
        )
        forced = NormalizationSelection(
            state="HUMAN_LOCAL_REVIEW_REQUIRED",
            reason="BOTH_PRE_WINDOWS_INVALID__POST_FEATURE_CONTEXT_USABLE",
            selected_pre_offsets_ev=None,
            preview_pre_offsets_ev=(-10.0, -5.0),
            diagnostics={
                "normalization_method": "automatic_approximate",
                "normalization_precision": "screening_level",
                "manual_review_recommended_for_critical_spectra": True,
                "publication_grade_normalization": False,
                "no_quality_promotion": True,
            },
        )
        with patch("xas_beamtime.analysis.select_normalization", return_value=forced):
            result = AnalysisEngine().analyze_series(
                [scan],
                self.v13,
                RuntimeLimits(8, 900),
            )[0]

        self.assertEqual(result.recommendation.value, "REVIEW_REQUIRED")
        self.assertIsNone(result.metrics.route)
        self.assertIsNone(result.predicted_n_quant)
        self.assertFalse(result.metrics.usable_protected_region)
        self.assertEqual(
            result.provenance["normalization_selector_state"],
            "HUMAN_LOCAL_REVIEW_REQUIRED",
        )
        self.assertTrue(result.provenance["no_quality_promotion"])

    def test_v13_decision_provenance_uses_v13_profile_label(self) -> None:
        metrics = QualityMetrics(
            0.004,
            0.004,
            0.006,
            2.0,
            2152.0,
            1.0,
            "full",
            "A",
            True,
            [],
        )
        outcome = DecisionEngine(self.v13).decide(
            metrics,
            1,
            60.0,
            [],
            RuntimeLimits(8, 900),
        )
        self.assertEqual(outcome.recommendation.value, "STOP")
        self.assertIn("P_K_XANES_v1.3", outcome.reason)
        self.assertIn("V13_TARGET_ATTAINED", outcome.reason_codes)


if __name__ == "__main__":
    unittest.main()
