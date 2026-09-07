# Real-time XAS Beamtime Decision Framework

[![Version](https://img.shields.io/badge/version-0.2.0-blue)](https://github.com/gchunhao/real-time-xas-beamtime-decision/releases)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/gchunhao/real-time-xas-beamtime-decision/actions/workflows/ci.yml/badge.svg)](https://github.com/gchunhao/real-time-xas-beamtime-decision/actions/workflows/ci.yml)

A local, profile-driven decision-support application for X-ray absorption spectroscopy (XAS) beamtime. It watches a beamline data folder, validates and parses completed scans, updates cumulative quality estimates, and presents an advisory recommendation for human review in a live browser interface.

The project translates an experimental quality-control workflow into reproducible, versioned software while preserving the scientist's authority over acquisition decisions.

> **Safety boundary:** v0.2 never controls or stops acquisition. The only automatic outputs are **CONTINUE**, **QL ONLY**, and **STOP RECOMMENDED**. An authorized beamtime team member—such as a beamline user, beamline scientist, or PI/experiment lead—makes the final decision.

## What it demonstrates

- Real-time scientific data ingestion with file-completion safeguards
- Profile-driven XANES quality metrics and transparent decision logic
- Human-in-the-loop review with reviewer identity and role provenance
- Reproducible algorithm/profile versioning in SQLite
- A Windows-friendly FastAPI and React/TypeScript application
- An extensible `(element, edge, scan type)` profile registry

## Workflow

```mermaid
flowchart TD
    A[Beamline data folder] --> B[Completion validation]
    B --> C[Parse and identify scan]
    C --> D[Profile-driven analysis]
    D --> E[Cumulative metrics and uncertainty]
    E --> F[Advisory recommendation]
    F --> G[Human review and final decision]
    G --> H[Versioned SQLite provenance]
```

## Project status

**v0.2.0 — operator-interface release, still a research prototype.** This release adds an Athena-style scientific workspace and a no-Python Windows desktop packaging path. The first implemented and frozen profile remains `P_K_XANES_v1.2`; v0.2 does not add or alter spectrum-processing algorithms. The application is suitable for demonstration, offline testing, and beamline-specific validation; it is not a validated instrument-control system.

### v0.2 operator experience

- Athena-style data tree, central spectrum canvas, decision inspector, and docked human-review workflow
- clear **Live beamtime** and **Offline review** entry points using the same traceable analysis pipeline
- native Windows folder chooser plus a manual path fallback
- beginner quick-start guidance and advanced controls hidden until requested
- Windows installer that creates a desktop shortcut and opens a self-contained application window
- persistent SQLite data under the current user's local application-data folder

## Relevance to beamline science

This project is a working example of translating user-side XAS expertise into beamline software and data infrastructure. It is particularly relevant to tender-energy spectroscopy workflows such as P K-edge XANES:

- **Real-time XAS decision support:** converts incoming scans into continuously updated, explainable recommendations during limited beamtime.
- **P K-edge XANES domain model:** implements a frozen `P_K_XANES_v1.2` profile with explicit energy windows, robust residual metrics, anomaly guards, and quantitative/qualitative routes.
- **Human-in-the-loop operation:** keeps the final decision with an authorized beamline user, beamline scientist, or PI/experiment lead and records reviewer role and rationale.
- **Traceable algorithms:** links every recommendation to the contributing scans, cumulative average, metric values, profile snapshot, and algorithm version.
- **Beamline extensibility:** separates acquisition-folder monitoring, parsing, calibration, analysis profiles, decisions, and provenance so future beamline adapters can evolve independently.

The current release demonstrates software architecture and scientific workflow design. It does not claim operational deployment or beamline validation.

## First supported profile

`P_K_XANES_v1.2` is frozen as a standalone YAML profile. Its implemented rules are:

- Route A: `Q_HF <= 0.45%`
- Route B: `0.45% < Q_HF <= 0.70%`, `Q_pre <= 0.55%`, `Q_post <= 0.95%`, `A_spike <= 3.0`
- initial averaging exponent `alpha = 0.50`
- quantitative first, then qualitative fallback, then stop
- protected XANES anomalies are flagged and never automatically removed
- automatic masking is confined to configured safe pre/post-edge regions
- local normalization remains available when full pre/post coverage is poor but the protected feature region is usable
- `N_quant` is the fastest of Route A and Route B
- scan and time limits use the stricter constraint; time is recomputed from measured scan durations

`Quantitative confirmed` is intentionally absent. Decisions use text-backed state keys and versioned snapshots, so that future state can be added without a schema redesign.

## Stack

- Python 3.10+
- FastAPI + Uvicorn
- SQLite
- NumPy + SciPy
- watchdog
- React + TypeScript + Vite

## Run on Windows without Python

Download `XAS-Beamtime-Decision-v0.2.0-Setup.exe` from a tagged release or the **Windows installer** GitHub Actions artifact. Run the installer, keep **Create a desktop shortcut** selected, then open **XAS Beamtime Decision** from the desktop or Start menu.

The installed application opens in its own window. Choose **Live beamtime** or **Offline review**, select the XAS data folder, and start the session. Closing the application window also stops its local service. User configuration, reference files, and `xas_feedback.sqlite3` are stored under `%LOCALAPPDATA%\XAS Beamtime Decision`, so uninstalling or upgrading does not silently replace review history.

## Run from source

For developers, install Python 3.10+ and Node.js 20+, then open PowerShell in this folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
cd frontend
npm install
npm run build
cd ..
xas-beamtime --config config\app.yaml
```

Open <http://127.0.0.1:8765>. For subsequent starts, `scripts\start_windows.ps1` performs the dependency/build check and starts the app.

The included `config/app.yaml` watches `test_data/incoming`. Change the folder in the UI or configuration for the beamline computer. Use a UNC path or drive path on Windows as needed.

## Test-data hook

Create a fresh deterministic P K-edge sequence:

```powershell
python scripts\generate_test_data.py --output test_data\incoming --scans 6
```

Each file contains explicit element, edge, scan type, sample, scan number, duration, and beamline metadata. The parser also falls back to filename inference when fields are missing.

## Tests

```powershell
python -m unittest discover -s tests -v
```

The tests cover frozen thresholds, metadata parsing, core metrics, protected/safe anomaly behavior, measured-duration constraints, advisory-only decisions, and the required database entities.

## Directory structure

```text
config/                         app and beamline calibration YAML
frontend/                       React/TypeScript working surface
reference_library/              external reference manifests/data
scripts/                        Windows launcher and data generator
test_data/incoming/             synthetic beamtime files
tests/                          backend unit/integration tests
xas_beamtime/
  analysis.py                   profile-driven metrics and averaging
  api.py                        FastAPI routes and static UI serving
  calibration.py                beamline-specific correction interface
  completion.py                 stable/readable/final-newline validation
  decision.py                   advisory state machine and N_quant
  parser.py                     universal text-table parser
  registry.py                   element/edge/scan-type profile registry
  service.py                    orchestration and in-memory live state
  storage.py                    SQLite provenance and human loop
  watcher.py                    watchdog folder events
  profiles/P_K_XANES/v1_2.yaml frozen profile
```

## Data and provenance

SQLite stores the requested first-version entities:

`experiment`, `sample`, `scan`, `cumulative_average`, `metrics`, `decision`, `artifact_flag`, `human_review`, `profile_version`, and `algorithm_version`.

Every automatic decision points to a cumulative average, frozen profile snapshot, and algorithm version. Every human review points back to that decision. This supports direct later comparison of algorithm prediction against reviewer judgment, with reviewer role retained.

From two scans onward, v0.1 also records a deterministic scan-bootstrap 95% variability band for `Q_HF`. `N_quant` remains explicitly labeled as an unconfirmed power-law projection using the frozen initial `alpha=0.50` assumption.

Human review records include scan inclusion/exclusion, weighting mode, normalization anchors, glitch confirmations/rejections, Q-ready/QL-ready/Below-QL rating, manual recommendation override, reviewer identity, reviewer role, and notes.

## Add another profile

Add a versioned YAML file under `xas_beamtime/profiles/<ELEMENT>_<EDGE>_<TYPE>/`. The registry matches the parsed `(element, edge, scan_type)` identity. Framework modules and the database do not require edits for another declarative profile with the existing analysis contract. New metric families can be registered behind the same profile/engine boundary in a later release.

## External reference library

Reference spectra remain outside application code. Copy `reference_library/references.example.yaml` to `references.yaml`, add curated datasets under that directory, and record citations/provenance in the manifest. v0.1 exposes this interface but does not yet perform reference fitting.

## Known v0.2 boundaries

- Text/CSV-style XAS files are supported; HDF5/NeXus adapters are future parser plugins.
- No acquisition-system or EPICS commands are implemented.
- No `Quantitative confirmed` state is exposed.
- Qualitative guardrails are profile configuration subject to later blind validation; frozen Route A/B definitions are unchanged.
- Beamline calibration must be validated locally before scientific use.

## Roadmap

### v0.2 — operator experience (current)

- Athena-style beginner workspace and native folder selection
- real-time beamtime and offline-review entry points
- Windows desktop executable, installer, and shortcut workflow
- unchanged P K-edge XANES v1.2 processing and decision rules

### v0.3 — validation and beamline integration layer

- Add blinded back-testing utilities and structured comparison of algorithm recommendations against human reviews
- Add import/export of experiment summaries and audit-ready decision reports
- Expand automated tests for malformed, partial, duplicated, and out-of-order files
- Add HDF5/NeXus parser adapters while retaining the universal text-table path
- Introduce read-only EPICS/acquisition metadata adapters; no automatic acquisition control
- Add beamline-specific calibration plugins and configuration validation
- Validate the Windows deployment workflow on representative beamline workstations

### v0.4 — additional spectroscopy profiles

- Validate the P K-edge profile against independent reference and beamtime datasets
- Register additional element/edge/scan-type profiles behind the same analysis contract
- Add curated reference-spectrum comparison with citation and provenance tracking
- Evaluate profile-specific uncertainty models after sufficient human-review data are collected

Any transition from advisory output to instrument control would require a separate safety review, explicit beamline authorization, and validation beyond this roadmap.
