#define AppVersion "2.0.0"
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

[Code]
const
  CabinetUninstallKey =
    'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B1A2E3A4-70D7-47BC-8E9A-26B9C1D25A5C}_is1';

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  PreviousDirectory: String;
  PreviousVersion: String;
  DataEnvironmentFile: String;
  ExitCode: Integer;
begin
  Result := '';
  if RegQueryStringValue(
       HKEY_CURRENT_USER,
       CabinetUninstallKey,
       'InstallLocation',
       PreviousDirectory) then
  begin
    PreviousDirectory := ExpandFileName(PreviousDirectory);
    if CompareText(PreviousDirectory, ExpandFileName(WizardDirValue)) <> 0 then
    begin
      Result :=
        'La mise à jour doit utiliser le dossier de l’installation existante : ' +
        PreviousDirectory +
        '. Modifiez le dossier de destination pour continuer.';
      exit;
    end;

    if not FileExists(PreviousDirectory + '\Cabinet.exe') or
       not FileExists(PreviousDirectory + '\compose.yaml') then
    begin
      Result :=
        'L’installation existante est incomplète. Aucun fichier n’a été remplacé.';
      exit;
    end;

    if not RegQueryStringValue(
         HKEY_CURRENT_USER,
         CabinetUninstallKey,
         'DisplayVersion',
         PreviousVersion) then
    begin
      Result :=
        'La version de l’installation existante est inconnue. Aucun fichier n’a été remplacé.';
      exit;
    end;

    if not Exec(
         PreviousDirectory + '\Cabinet.exe',
         '--preupdate "' + PreviousDirectory + '" "' + PreviousVersion + '"',
         PreviousDirectory,
         SW_HIDE,
         ewWaitUntilTerminated,
         ExitCode) then
    begin
      Result :=
        'Impossible de lancer la sauvegarde préalable. Aucun fichier n’a été remplacé.';
      exit;
    end;
    if ExitCode <> 0 then
    begin
      Result :=
        'La sauvegarde ou les contrôles préalables ont échoué. ' +
        'L’installation est annulée et les fichiers existants sont conservés.';
      exit;
    end;
  end
  else
  begin
    DataEnvironmentFile :=
      ExpandConstant('{localappdata}\Cabinet\.env');
    if FileExists(DataEnvironmentFile) then
    begin
      Result :=
        'Une configuration Cabinet existe mais aucune installation enregistrée ' +
        'n’a été identifiée. Pour protéger la base, contactez le support avant ' +
        'de continuer.';
    end;
  end;
end;
