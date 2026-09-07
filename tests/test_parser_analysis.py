from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from xas_beamtime.analysis import AnalysisEngine
from xas_beamtime.models import RuntimeLimits
from xas_beamtime.parser import UniversalXASParser
from xas_beamtime.registry import ProfileRegistry


class ParserAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = ProfileRegistry().get("P_K_XANES_v1.2")

    def test_metadata_and_metrics(self) -> None:
        project = Path(__file__).parent.parent
        path = project / "test_data" / "incoming" / "apatite_scan-001.dat"
        scan = UniversalXASParser().parse(path)
        self.assertEqual(scan.metadata.element, "P")
        self.assertEqual(scan.metadata.edge, "K")
        self.assertEqual(scan.metadata.scan_type, "XANES")
        self.assertEqual(scan.metadata.sample_id, "apatite")
        self.assertEqual(scan.metadata.scan_number, 1)
        self.assertAlmostEqual(scan.metadata.duration_seconds or 0, 93.7)
        result = AnalysisEngine().analyze_series([scan], self.profile, RuntimeLimits(8, 900))[0]
        self.assertTrue(2148 < (result.metrics.e0 or 0) < 2157)
        self.assertIsNotNone(result.metrics.q_hf)
        self.assertTrue(result.provenance["protected_anomalies_auto_removed"] is False)

    def test_protected_region_is_never_auto_masked(self) -> None:
        energy = np.arange(2140, 2185, .15)
        aligned = np.vstack([np.sin(energy / 4)])
        regions = AnalysisEngine._regions(2152, self.profile)
        protected_index = np.argmin(abs(energy - 2161))
        safe_index = np.argmin(abs(energy - 2144))
        aligned[0, protected_index] += 10
        aligned[0, safe_index] += 10
        cleaned, anomalies = AnalysisEngine._detect_and_mask(energy, aligned, regions, self.profile)
        protected = [a for a in anomalies if a.protected and abs(a.energy - energy[protected_index]) < .08]
        safe = [a for a in anomalies if not a.protected and abs(a.energy - energy[safe_index]) < .08]
        self.assertTrue(protected)
        self.assertFalse(protected[0].automatically_masked)
        self.assertEqual(cleaned[0, protected_index], aligned[0, protected_index])
        self.assertTrue(safe)
        self.assertTrue(safe[0].automatically_masked)
        self.assertNotEqual(cleaned[0, safe_index], aligned[0, safe_index])


if __name__ == "__main__":
    unittest.main()
