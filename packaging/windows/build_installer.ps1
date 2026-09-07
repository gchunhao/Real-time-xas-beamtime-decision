$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root

function Assert-LastExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

Write-Host "[1/5] Installing frontend dependencies"
Push-Location frontend
npm ci
Assert-LastExitCode "npm ci"
npm run test
Assert-LastExitCode "Frontend tests"
npm run build
Assert-LastExitCode "Frontend production build"
Pop-Location

Write-Host "[2/5] Installing Python build dependencies"
python -m pip install --upgrade pip
Assert-LastExitCode "pip upgrade"
python -m pip install -r requirements.txt -r packaging/windows/requirements-build.txt
Assert-LastExitCode "Python build dependency installation"

Write-Host "[3/5] Running backend tests"
python -m unittest discover -s tests -v
Assert-LastExitCode "Backend tests"

Write-Host "[4/5] Building Windows application"
python -m PyInstaller --noconfirm --clean --distpath build/dist --workpath build/pyinstaller packaging/windows/XASFramework.spec
Assert-LastExitCode "PyInstaller build"
$Smoke = Start-Process -FilePath "build\dist\XASFramework\XASFramework.exe" -ArgumentList "--smoke-test" -Wait -PassThru
if ($Smoke.ExitCode -ne 0) {
    throw "Packaged application smoke test failed with exit code $($Smoke.ExitCode)"
}

Write-Host "[5/5] Building installer"
$Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $Iscc)) { throw "Inno Setup 6 was not found: $Iscc" }
& $Iscc "packaging\windows\XAS_Framework_v0.2.iss"
Assert-LastExitCode "Inno Setup build"

$Setup = Join-Path $Root "build\installer\XAS_Framework_v0.2_Setup.exe"
if (-not (Test-Path $Setup)) { throw "Installer was not generated" }
Get-FileHash $Setup -Algorithm SHA256
Write-Host "Installer ready: $Setup"
