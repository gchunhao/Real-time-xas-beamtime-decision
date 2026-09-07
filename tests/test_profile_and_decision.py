from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from xas_beamtime.decision import DecisionEngine
from xas_beamtime.models import QualityMetrics, RuntimeLimits, ScanMetadata, Spectrum
from xas_beamtime.registry import ProfileRegistry


class ProfileAndDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = ProfileRegistry().get("P_K_XANES_v1.2")

    def test_frozen_thresholds(self) -> None:
        self.assertEqual(self.profile.get("status"), "frozen")
        self.assertEqual(self.profile.get("quality.route_a.q_hf_max"), 0.0045)
        self.assertEqual(self.profile.get("quality.route_b.q_hf_max"), 0.0070)
        self.assertEqual(self.profile.get("quality.route_b.q_pre_max"), 0.0055)
        self.assertEqual(self.profile.get("quality.route_b.q_post_max"), 0.0095)
        self.assertEqual(self.profile.get("quality.route_b.a_spike_max"), 3.0)
        self.assertEqual(self.profile.get("averaging.initial_alpha"), 0.50)

    def test_stricter_time_limit_uses_measured_duration(self) -> None:
        metrics = QualityMetrics(.009, .004, .006, 2.5, 2152, 1, "full", None, True, [])
        scan = Spectrum(np.array([1, 2]), np.array([0, 1]), ScanMetadata("x", duration_seconds=80))
        outcome = DecisionEngine(self.profile).decide(metrics, 2, 160, [scan, scan], RuntimeLimits(10, 200))
        self.assertEqual(outcome.remaining_scan_budget, 8)
        self.assertEqual(outcome.remaining_time_seconds, 40)
        self.assertEqual(outcome.recommendation.value, "QL ONLY")

    def test_route_a_is_stop_recommended_not_confirmed(self) -> None:
        metrics = QualityMetrics(.004, .02, None, 5, 2152, 1, "local", "A", True, [])
        outcome = DecisionEngine(self.profile).decide(metrics, 3, 200, [], RuntimeLimits(8, 900))
        self.assertEqual(outcome.recommendation.value, "STOP RECOMMENDED")
        self.assertIn("human confirmation", outcome.reason)


if __name__ == "__main__":
    unittest.main()
