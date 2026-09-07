$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Push-Location (Join-Path $ProjectRoot "frontend")
npm ci
npm run build
Pop-Location

Push-Location $ProjectRoot
python -m pip install -e "${ProjectRoot}[desktop]"
python -m PyInstaller --clean --noconfirm (Join-Path $ProjectRoot "packaging\xas_beamtime.spec")

$Iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($Iscc) {
    & $Iscc.Source (Join-Path $ProjectRoot "packaging\windows\installer.iss")
    Write-Host "Installer created in $ProjectRoot\release"
} else {
    Write-Host "Inno Setup was not found. The portable application is in $ProjectRoot\dist\XASBeamtimeDecision"
}
Pop-Location
