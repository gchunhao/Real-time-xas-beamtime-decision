# Changelog

All notable changes to this project will be documented here.

## [0.2.0] - 2026-09-07

### Added

- Athena-style operator workspace with a scan tree, spectrum canvas, decision inspector, and docked review workflow
- distinct live-beamtime and offline-review entry points with beginner quick-start guidance
- native local folder chooser with a manual path fallback
- PyWebView desktop shell that closes the local server with the application window
- PyInstaller and Inno Setup build files plus a Windows installer GitHub Actions workflow
- per-user persistent configuration, reference-library copy, and SQLite data location on Windows

### Changed

- Reorganized advanced normalization controls behind an explicit advanced-view toggle
- Clarified throughout the interface that beamline users and other authorized reviewers may make the human decision
- Kept all `P_K_XANES_v1.2` spectrum-processing and advisory-decision rules unchanged

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
