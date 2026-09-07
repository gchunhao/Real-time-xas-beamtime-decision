#define AppName "XAS Beamtime Decision"
#define AppVersion "0.2.0"
#define AppPublisher "Chunhao Gu"
#define AppExeName "XASBeamtimeDecision.exe"

[Setup]
AppId={{6D1D996E-8AF4-49CA-BF96-FAD4A1D3A52D}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\XAS Beamtime Decision
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=..\..\release
OutputBaseFilename=XAS-Beamtime-Decision-v{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExeName}

[Files]
Source: "..\..\dist\XASBeamtimeDecision\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
