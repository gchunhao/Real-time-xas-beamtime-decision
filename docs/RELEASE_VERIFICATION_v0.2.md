# XAS Framework v0.2 Release Verification

Date: 2026-09-07

## Verified locally

- React/TypeScript production build: PASS
- Frontend API/formatter tests: 5/5 PASS
- Python backend/profile/storage/workflow/packaging tests: 17/17 PASS
- FastAPI + static UI + workflow/scheduler resource smoke check: PASS
- Desktop launcher source-mode `--smoke-test`: PASS
- Scheduler safety assertion (`acquisition_control_enabled=false`): PASS
- Frozen `P_K_XANES v1.2` SHA-256:
  `90acc2b45bd7412919b3ed60945ad25bfe94105ecfef9c0b407145ad6dada9c1`

## Windows installer verification gate

The final PE installer must be built on Windows. The repository contains a
reproducible `windows-latest` workflow and local PowerShell build script. Both
run the packaged executable with `--smoke-test` before Inno Setup creates
`XAS_Framework_v0.2_Setup.exe`.

Required successful Windows artifact checks:

1. PyInstaller produces `build/dist/XASFramework/XASFramework.exe`.
2. The packaged application returns `/api/workflow` and `/api/scheduler/state`.
3. The safety check confirms physical acquisition control remains disabled.
4. Inno Setup produces `build/installer/XAS_Framework_v0.2_Setup.exe`.
5. The installer includes a default-selected desktop shortcut task.

No Windows executable is claimed as verified until that Windows build job has
completed successfully.
