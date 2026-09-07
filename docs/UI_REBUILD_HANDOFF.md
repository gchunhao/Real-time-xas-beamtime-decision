# v0.2 Frozen UI Rebuild Handoff

## Status of this source package

Implemented in the React/TypeScript frontend. This document remains the binding
acceptance checklist for the frozen v0.2 UI and terminology.

## Frozen product semantics

- Automated Decision is primary.
- **Reviewer Decision** is the exact official term and is supervisory/override.
- Reviewer silence means no override, not approval.
- Authorized reviewers include beamline users as well as beamline scientists.
- All v0.2 execution is simulation-only; no acquisition or EPICS command is sent.
- `P_K_XANES v1.2` is frozen and must not be edited.
- ADP v1.0 remains a separately versioned shadow policy and must be labeled
  **ADP Shadow** until promoted through later validation.

## Frozen UI target

The approved mockup uses a desktop scientific-workbench shell with these named
surfaces:

1. Home / Startup & Mode Selection
2. Live Workspace
3. Review Queue
4. Data Browser
5. Overlay Compare
6. Offline Analysis / Offline Retrospective Review
7. Audit Logs
8. Settings

The first implementation pass may keep advanced offline retrospective behavior
inside Review Queue / Reviewer Decision, but the final navigation and naming
must remain aligned with the approved mockup.

### Home

- Live Mode
- Offline Retrospective Review
- Tutorial / Demo
- Recent Projects

### Live Workspace

- Run Status, Current Sample, Queue Progress, Review Queue, Scheduler State
- Sample Queue with running/queued/review/completed status
- Current Scan View
- Automation Workflow:
  New Scan Detected → Parse & Process → QC Analysis → ADP Shadow →
  Automated Decision → Scheduler Action
- Sample Action and Scheduler Action remain visibly separate

### QC / decision view

- XAS Spectrum & QC Results
- QC Metrics
- Quality Prediction
- Automated Decision with reasoning, marginal gain/additional scans,
  confidence, resource constraint, sample action, and scheduler action
- **Reviewer Decision** with Automatic — No override, Override Decision,
  Pause Automation, Add Note, and View Audit

### Overlay / retrospective view

- Dataset Selection
- Overlay Plot
- Difference Plot
- Original Automated Decision and confidence
- Retrospective/hindsight Reviewer Decision
- Save to an independent human-in-the-loop feedback dataset
- Previous Review History

## Existing backend resources to reuse

- projects and sessions
- samples and scans
- decisions
- reviews and reviewer adjudication
- review queue
- audit events
- scheduler simulation state
- scan disposition and usable/physical scan counts

Sample Queue and Automation Workflow should initially be derived as read-only
projections from these resources. Add a small presentation endpoint only when a
required state cannot be derived cleanly. Do not redesign the scientific engine
or frozen profile to support the UI.

## Next delivery sequence

1. Rebuild the React frontend against the frozen mockup.
2. Add only necessary workflow projections without changing scientific logic.
3. Run frontend/backend tests and end-to-end smoke checks.
4. Add Windows PyInstaller and Inno Setup packaging.
5. Build and verify `XAS_Framework_v0.2_Setup.exe` on Windows.
6. Retain a clean source ZIP for continued development.
