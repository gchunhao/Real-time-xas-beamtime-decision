$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root

Write-Host "[1/5] Installing frontend dependencies"
Push-Location frontend
npm ci
npm run test
npm run build
Pop-Location

Write-Host "[2/5] Installing Python build dependencies"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r packaging/windows/requirements-build.txt

Write-Host "[3/5] Running backend tests"
python -m unittest discover -s tests -v

Write-Host "[4/5] Building Windows application"
python -m PyInstaller --noconfirm --clean --distpath build/dist --workpath build/pyinstaller packaging/windows/XASFramework.spec
& "build\dist\XASFramework\XASFramework.exe" --smoke-test

Write-Host "[5/5] Building installer"
$Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $Iscc)) { throw "Inno Setup 6 was not found: $Iscc" }
& $Iscc "packaging\windows\XAS_Framework_v0.2.iss"

$Setup = Join-Path $Root "build\installer\XAS_Framework_v0.2_Setup.exe"
if (-not (Test-Path $Setup)) { throw "Installer was not generated" }
Get-FileHash $Setup -Algorithm SHA256
Write-Host "Installer ready: $Setup"
