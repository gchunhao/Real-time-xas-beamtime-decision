# P_K_XANES v1.3 Freeze Record

Status: **FROZEN**

Freeze date: 2026-09-08

## Scientific contract

### E0
- Search window: **2147.5–2152.9 eV**
- Interpolation step: **0.15 eV**
- E0: smoothed first-derivative maximum
- Savitzky-Golay: **11 points, polynomial order 3**
- Beamline energy calibration, when configured, is applied before E0 determination.

### Normalization selector
- `WIDE_PRE`: **E0-20 to E0-10 eV**
- `NEAR_PRE`: **E0-10 to E0-5 eV**
- Four states:
  - `WIDE_PRE`
  - `NEAR_PRE`
  - `HUMAN_LOCAL_REVIEW_REQUIRED`
  - `REVIEW_REQUIRED`

### Normalization-context diagnostics
Post-edge context:
- region: **E0+27 to E0+50 eV**
- `post_norm_resid <= 0.018`
- `post_stability <= 0.27`

Feature context:
- region: **E0+5 to E0+23 eV**
- `feature_noise_norm <= 0.0122`
- `feature_A_spike <= 6.1`

### Scientific quality routes
Route thresholds are unchanged from v1.2.

Route A:
- `Q_HF <= 0.0045`

Route B:
- `Q_HF <= 0.0070`
- `Q_pre <= 0.0055`
- `Q_post <= 0.0095`
- `A_spike <= 3.0`

## Mandatory safeguards

### NO QUALITY PROMOTION
Normalization-path state is independent of scientific quality.

`HUMAN_LOCAL_REVIEW_REQUIRED` and `REVIEW_REQUIRED`:
- cannot upgrade Below-QL / QL-ready / Q-ready status;
- cannot clear protected anomalies;
- cannot override adjudicated human labels;
- cannot imply publication-grade normalization;
- suppress automatic Route and N_quant claims pending expert review.

### Protected-region independence
Protected anomalies remain visible and are never automatically removed.

### Normalization precision boundary
Automatic normalization is:
- `automatic_approximate`
- `screening_level`
- intended for beamtime decision support, not final publication-grade processing.

Critical spectra require expert verification.

## Validation record

### E0 paired replay
37 cumulative-prefix states:
- Route changes: **0**

### Full-selector route-stability replay
37 cumulative-prefix states:
- automatic-normalization states: **16**
- review states: **21**
- Route A/B changes among automatic states: **0**
- N_quant changes among automatic states: **3**

The N_quant changes did not alter Route A/B classification.

### Pre-freeze review-state audit
- `HUMAN_LOCAL_REVIEW_REQUIRED`: **18**
- `REVIEW_REQUIRED`: **3**
- known Below-QL group allowed into local-review path: `140ky_RA3`, retained as Below-QL by NO QUALITY PROMOTION
- all three REVIEW_REQUIRED cases were scientifically supported

### Implementation / CI
The GitHub candidate implementation passed backend tests, frontend tests, and frontend production build before freeze.

The private 37-prefix validation corpus is not committed to the public repository. Public CI verifies the implementation path using repository fixtures/synthetic regression tests; the private corpus is replayed separately against the source-synchronized frozen contract.

## Energy-calibration provenance
The analysis provenance exposes:
- beamline
- calibration configured/applied status
- energy offset
- energy scale
- calibration file/schema
- calibration standard/timestamp when present
- calibration notes

Processing order:
`E_raw -> E_calibrated -> E0 -> normalization selector -> metrics`

## Frozen source snapshot

- `xas_beamtime/profiles/P_K_XANES/v1_3.yaml`: Git blob `58a36b8a5f0c06c8b00c0b798516433671e7e5a8`
- `xas_beamtime/analysis.py`: Git blob `9317dfae23d82c174c82b3e27ce950fe42914f66`
- `xas_beamtime/normalization_selector.py`: Git blob `46d723b5d8d95596e3ad88f1cc111da668dba501`
- `xas_beamtime/decision.py`: Git blob `07bc9a03d04a375486fd61211fda42309f596927`
- `xas_beamtime/service.py`: Git blob `f036789b4441cf15e5edfd1a04464b250348a318`
- `frontend/src/App.tsx`: Git blob `acbb764e94411dc60d4bc8712e0a1c6607824049`
- `tests/test_v13_freeze_candidate.py`: Git blob `8132baa90ed6f41c9458a23d734ef22d79ad69a7`

Analysis algorithm version:
- `xas-analysis-0.2.0`

## Reproducibility and rollout
- `P_K_XANES_v1.2` remains immutable.
- `P_K_XANES_v1.3` is the latest frozen P K-edge XANES profile.
- Runtime configuration remains on v1.2 until an explicit rollout changes the selected profile.
- ADP remains separately versioned and is not part of this profile freeze.
- No physical acquisition or EPICS control is enabled.

## Remaining validation limitations
Freezing means this algorithm version is immutable and reproducible; it does **not** mean universal validation.

Still desirable:
- independent/blinded external-corpus validation;
- beamline-specific local energy-calibration validation;
- broader multi-beamline performance characterization.

These limitations must not be removed from user-facing scientific claims.
