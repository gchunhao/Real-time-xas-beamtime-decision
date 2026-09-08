# Changelog

## Unreleased

- Marked v0.2 explicitly as an incomplete research prototype pending Windows acceptance testing.
- Replaced default-browser launch with a native pywebview desktop shell backed by the local FastAPI service.
- Added a deliberately narrow desktop bridge for native folder and multi-file selection; no hardware-control method is exposed.
- Added Live startup folder selection and a complete Offline batch-import path for folders or multiple XAS files.
- Bundled the synthetic demonstration dataset and connected the Home demo action to the real Offline pipeline.
- Grouped each offline import into one project/session workspace and ran imported files through the same parser, QC, decision, audit, and provenance pipeline.
- Added visible import summaries, native Browse controls, runtime mode labels, and current-session filtering in the desktop UI.

### P_K_XANES v1.3 frozen scientific profile

- Froze `P_K_XANES_v1.3` after implementation-level regression, UI/provenance verification, and freeze audit.
- Narrowed the P K-edge E0 search window to 2147.5–2152.9 eV.
- Added dual pre-edge selection: `WIDE_PRE` (E0-20 to E0-10 eV) and `NEAR_PRE` (E0-10 to E0-5 eV).
- Added four normalization-path states: `WIDE_PRE`, `NEAR_PRE`, `HUMAN_LOCAL_REVIEW_REQUIRED`, and `REVIEW_REQUIRED`.
- Added normalization-context diagnostics for post-edge and feature regions.
- Added mandatory `NO QUALITY PROMOTION` behavior and independent protected-anomaly review.
- Marked automatic normalization as approximate, screening-level decision support rather than publication-grade processing.
- Added energy-calibration provenance and operator UI visibility.
- Preserved all Route A/Route B thresholds from v1.2; full-selector replay produced zero Route changes across automatic-normalization states.
- Retained `P_K_XANES_v1.2` unchanged for reproducibility.
- Rolled the prototype runtime configuration forward to the frozen `P_K_XANES_v1.3`; v1.2 remains available unchanged.
- Fixed Overall QC to read `metrics.route` and represent review-gated spectra without a false Good state.
- Distinguished predicted total scans from additional scans needed in the operator UI.
- Replaced the hard-coded Running badge with decision-derived Completed, Running, Review Required, or Reacquire status.
- Returned single-scan energy, raw, and normalized arrays on one analysis grid in both state and spectrum APIs.

- Close SQLite resources deterministically so Windows can remove temporary test databases.
- Fixed installed shortcut startup when the windowed executable has no console streams;
  launcher output is now written to `%LOCALAPPDATA%\XAS Framework\runtime\launcher.log`.
- Made the Windows packaged-application smoke test wait for the GUI executable and
  validate its real exit code instead of accepting an asynchronous launch.

- Fixed the Windows bundle missing SciPy's vendored Array API compatibility
  modules, which caused the installed application to fail while importing
  `scipy.signal`.
- Pinned the Windows numeric/build toolchain used by the installer workflow.
- Made every native build, test, packaged smoke-test, and installer command
  fail the workflow immediately when it returns a non-zero exit code.
- Kept `P_K_XANES v1.2` and all scientific decision behavior unchanged.

## [0.2.0] - 2026-09-07 — frozen UI integration and Windows packaging

- Rebuilt the React/TypeScript interface to the frozen v0.2 Athena-like layout.
- Added the eight frozen navigation surfaces and full Automated Decision /
  Reviewer Decision terminology.
- Added read-only `/api/workflow` projection with Sample Action, Scheduler
  Action, ADP Shadow, queue counts, and workflow-stage status.
- Added PyInstaller + Inno Setup packaging, a default desktop shortcut,
  packaged safety smoke test, and GitHub Actions Windows build workflow.
- Kept all execution simulation-only and `P_K_XANES v1.2` unchanged.

## v0.2.0-dev checkpoint — resource API integration before frozen-UI rebuild

> This checkpoint validates the resource-style frontend/backend connection. Its
> current visual shell is interim and does not yet implement the frozen v0.2 UI
> mockup. The next development stage rebuilds the frontend against that mockup.

- Replaced the scaffold dashboard with an interim five-surface workspace used to validate resource integration: Home, Live Workspace, Review Queue, Data Browser / Overlay Compare, and Offline Analysis.
- Added a typed React/TypeScript API client and shared polling/mutation state for project, session, sample, scan, decision, review queue, human review, audit, and scheduler resources.
- Added Review Queue tabs for pending/resolved/superseded items with side-by-side Automated Decision and Reviewer Decision views.
- Added reviewer identity, role/authority, context, quality rating, notes, explicit override, and Pause Automation (`REVIEW_REQUIRED`) controls. Beamline users and other authorized roles can review; review is not restricted to beamline scientists.
- Added live scheduler state with explicit simulation-only and disconnected-beamline labels.
- Added resource browsing, scan counters and Previous/Next controls, scan disposition updates, normalized spectrum overlay loading, decision status, and audit status.
- Preserved scan/raw/normalized/average review, overlay, E0/region visibility, averaging mode, scan inclusion, local-normalization anchors, and glitch confirmation/rejection controls.
- Added frontend resource-contract and formatter tests; production frontend build output is included.
- No scientific profile or threshold changes. `P_K_XANES v1.2` remains frozen.

## 0.2.0-dev

- Replaced legacy QL-only/stop-recommended decision vocabulary with CONTINUE / STOP / REACQUIRE / REVIEW_REQUIRED.
- Separated scientific decision from resource constraints and effective scheduler action.
- Added SampleAction, SchedulerAction, AutoExecutionEligibility, scan disposition, reviewer context/level, and audit events.
- Added ADP v1.0 shadow trend prediction with alpha_pred capped at 0.5 and long-range forecast suppression.
- Added scheduler simulation adapter; physical acquisition control remains disabled.
- Kept reviewer reanalysis separate from production in-memory state.
- Added immutable reviewer records with higher-level adjudication and same-level conflict handling.
- Added SQLite v0.2 migration coverage and backend decision/storage tests.
- Wired `ScanDisposition` into the live production pipeline: only `USABLE` scans enter the production series; unresolved `SUSPECT`/`PENDING_REVIEW` scans block automatic sample decisions conservatively.
- Added sample-level review queue persistence and lifecycle (`PENDING` / `RESOLVED` / `SUPERSEDED`).
- REVIEW_REQUIRED now holds only the affected logical sample while the simulated scheduler advances to the next sample.
- Added Project → Session → Sample → Scan persistence/resource APIs while retaining the legacy experiment table for migration compatibility.
- Added resource-style FastAPI contracts for projects, sessions, samples, scans, decisions, review queue, audit, and scheduler state.
- Added scan-disposition PATCH API and replacement-link provenance.
- Separated reviewer quality ratings from reviewer decision overrides; a quality rating alone no longer resolves a REVIEW_REQUIRED queue item.
- Added physical vs usable scan counts to stored analysis state.
- Added focused service-pipeline and API-contract tests.

All notable changes to this project will be documented here.

## [0.1.0] - 2026-09-07

### Added

- Local watchdog-based scan-folder monitoring and file-completion validation
- Universal text-table parser with metadata and filename inference
- Frozen `P_K_XANES_v1.2` profile and profile registry
- Cumulative quality metrics, uncertainty estimates, and advisory decisions
- FastAPI backend and React/TypeScript live interface
- SQLite provenance model and human-review workflow
- Synthetic P K-edge test sequence and automated backend tests
- Windows startup workflow and configuration examples
