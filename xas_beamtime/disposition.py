from __future__ import annotations

from dataclasses import dataclass

from .models import ScanDisposition, Spectrum


@dataclass(slots=True)
class DispositionAssessment:
    disposition: ScanDisposition
    reason: str | None = None
    reason_code: str | None = None


class ScanDispositionPolicy:
    """Conservative v0.2 scan-disposition policy.

    This layer intentionally does not invent new quantitative QC thresholds.
    Frozen P_K_XANES v1.2 remains the scientific QC engine. Automatic
    disposition is limited to provenance/grouping situations where the scan
    cannot safely enter a logical-sample average until a reviewer confirms the
    grouping. All other scans enter as USABLE unless a reviewer explicitly
    changes their disposition.
    """

    def assess_new_scan(self, spectrum: Spectrum) -> DispositionAssessment:
        metadata = spectrum.metadata
        if metadata.requires_grouping_confirmation:
            return DispositionAssessment(
                ScanDisposition.PENDING_REVIEW,
                reason="Logical-sample grouping requires reviewer confirmation",
                reason_code="GROUPING_CONFIRMATION_REQUIRED",
            )
        return DispositionAssessment(ScanDisposition.USABLE)

    @staticmethod
    def blocks_automatic_sample_decision(disposition: ScanDisposition) -> bool:
        return disposition in {ScanDisposition.SUSPECT, ScanDisposition.PENDING_REVIEW}
