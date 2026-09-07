from __future__ import annotations

import unittest

import numpy as np

from xas_beamtime.decision import DecisionEngine
from xas_beamtime.models import (
    AutoExecutionEligibility,
    QualityMetrics,
    ResourceConstraint,
    RuntimeLimits,
    SampleAction,
    SchedulerAction,
    ScanMetadata,
    Spectrum,
)
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

    def test_resource_exhaustion_does_not_change_scientific_decision(self) -> None:
        metrics = QualityMetrics(.009, .004, .006, 2.5, 2152, 1, "full", None, True, [])
        scan = Spectrum(np.array([1, 2]), np.array([0, 1]), ScanMetadata("x", duration_seconds=80))
        outcome = DecisionEngine(self.profile).decide(metrics, 2, 160, [scan, scan], RuntimeLimits(10, 200))
        self.assertEqual(outcome.remaining_scan_budget, 8)
        self.assertEqual(outcome.remaining_time_seconds, 40)
        self.assertEqual(outcome.recommendation.value, "CONTINUE")
        self.assertEqual(outcome.resource_constraint, ResourceConstraint.TIME_LIMIT_EXHAUSTED)
        self.assertEqual(outcome.sample_action, SampleAction.ACQUIRE_MORE)
        self.assertEqual(outcome.scheduler_action, SchedulerAction.STAY_ON_SAMPLE)
        self.assertEqual(outcome.effective_scheduler_action, SchedulerAction.ADVANCE_TO_NEXT_SAMPLE)
        self.assertEqual(outcome.auto_execution_eligibility, AutoExecutionEligibility.BLOCKED)

    def test_route_a_is_automatic_stop_without_human_approval(self) -> None:
        metrics = QualityMetrics(.004, .02, None, 5, 2152, 1, "local", "A", True, [])
        outcome = DecisionEngine(self.profile).decide(metrics, 3, 200, [], RuntimeLimits(8, 900))
        self.assertEqual(outcome.recommendation.value, "STOP")
        self.assertNotIn("human confirmation", outcome.reason.lower())
        self.assertEqual(outcome.sample_action, SampleAction.FINISH_SAMPLE)
        self.assertEqual(outcome.scheduler_action, SchedulerAction.ADVANCE_TO_NEXT_SAMPLE)
        self.assertEqual(outcome.auto_execution_eligibility, AutoExecutionEligibility.ELIGIBLE)

    def test_prediction_uses_observed_trend_and_caps_alpha(self) -> None:
        engine = DecisionEngine(self.profile)
        prior = [QualityMetrics(.012, .01, .01, 2.0, 2152, 1, "full", None, True, [])]
        current = QualityMetrics(.008, .009, .009, 2.0, 2152, 1, "full", None, True, [])
        outcome = engine.decide(current, 2, 160, [], RuntimeLimits(10, 2000), prior_metrics=prior)
        self.assertIsNotNone(outcome.alpha_global)
        self.assertIsNotNone(outcome.alpha_recent)
        self.assertIsNotNone(outcome.alpha_pred)
        self.assertLessEqual(outcome.alpha_pred or 1, 0.5)

    def test_prediction_is_not_truncated_above_four_total_scans(self) -> None:
        metrics = QualityMetrics(.012, .004, .006, 4.0, 2152, 1, "full", None, True, [])
        scan = Spectrum(np.array([1, 2]), np.array([0, 1]), ScanMetadata("x", duration_seconds=80))
        outcome = DecisionEngine(self.profile).decide(metrics, 1, 80, [scan], RuntimeLimits(20, 5000))
        self.assertEqual(outcome.predicted_n_quant, 8)
        self.assertEqual(outcome.recommendation.value, "CONTINUE")

    def test_review_required_routes_sample_hold_and_scheduler_advance(self) -> None:
        outcome = DecisionEngine(self.profile).review_required(
            "Independent reproducibility evidence is unstable",
            ["SHAPE_INSTABILITY"],
            suggested_reviewer_action="CHECK_ACQUISITION_CONDITIONS",
        )
        self.assertEqual(outcome.recommendation.value, "REVIEW_REQUIRED")
        self.assertEqual(outcome.sample_action, SampleAction.HOLD_FOR_REVIEW)
        self.assertEqual(outcome.scheduler_action, SchedulerAction.ADVANCE_TO_NEXT_SAMPLE)
        self.assertEqual(outcome.auto_execution_eligibility, AutoExecutionEligibility.BLOCKED)


if __name__ == "__main__":
    unittest.main()
