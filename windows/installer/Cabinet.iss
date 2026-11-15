#define AppVersion "1.0.0"
#define PayloadDir AddBackslash(SourcePath) + "..\distribution\payload"

[Setup]
AppId={{B1A2E3A4-70D7-47BC-8E9A-26B9C1D25A5C}
AppName=Cabinet médical
AppVersion={#AppVersion}
AppPublisher=Cabinet médical
DefaultDirName={localappdata}\Programs\Cabinet
DefaultGroupName=Cabinet médical
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
OutputDir={#SourcePath}..\distribution
OutputBaseFilename=Cabinet-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Cabinet.exe
CloseApplications=yes

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\Cabinet médical"; Filename: "{app}\Cabinet.exe"

[Run]
Filename: "{app}\Cabinet.exe"; Description: "Démarrer Cabinet médical"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "{app}\Cabinet.exe"; Parameters: "--stop"; RunOnceId: "StopCabinetContainers"; Flags: runhidden waituntilterminated skipifdoesntexist
