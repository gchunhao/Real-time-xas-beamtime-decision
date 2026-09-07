#define MyAppName "XAS Framework"
#define MyAppVersion "0.2.0"
#define MyAppPublisher "Chunhao Gu"
#define MyAppExeName "XASFramework.exe"

[Setup]
AppId={{B79BC650-40F8-4D48-A145-88C74E2116A2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\XAS Framework
DefaultGroupName=XAS Framework
DisableProgramGroupPage=yes
OutputDir=..\..\build\installer
OutputBaseFilename=XAS_Framework_v0.2_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: checkedonce

[Files]
Source: "..\..\build\dist\XASFramework\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\XAS Framework"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\XAS Framework"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch XAS Framework"; Flags: nowait postinstall skipifsilent
