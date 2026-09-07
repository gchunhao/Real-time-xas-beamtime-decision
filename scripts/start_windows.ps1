$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not (Test-Path ".venv")) { py -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -e .
if (-not (Test-Path "frontend\node_modules")) { Push-Location frontend; npm install; Pop-Location }
Push-Location frontend
npm run build
Pop-Location
& .\.venv\Scripts\xas-beamtime.exe --config config\app.yaml
