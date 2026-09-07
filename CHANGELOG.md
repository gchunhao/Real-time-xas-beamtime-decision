# Changelog

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
