; Inno Setup: baut aus der PyInstaller-Ausgabe einen Windows-Installer.
;
; Aufruf (der Workflow macht das selbst):
;   iscc /DVersion=0.1.0 packaging\comicdesk.iss
;
; Bewusst eine Installation ohne Administratorrechte: sie landet unter
; %LOCALAPPDATA%. Das erspart die Nachfrage der Benutzerkontensteuerung,
; die bei einer unsignierten Datei ohnehin nach dem Herausgeber fragt und
; "Unbekannt" anzeigt.

#ifndef Version
  #define Version "0.0.0"
#endif

#define AppName "ComicDesk"
#define AppPublisher "ComicDesk"
#define AppURL "https://github.com/aaaaaprvdgrwwelt/comicdesk"

[Setup]
AppId={{8E2F1C64-9A3D-4F27-9B41-0C7D5E6A8B13}
AppName={#AppName}
AppVersion={#Version}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=ComicDesk-{#Version}-Windows-Setup
SetupIconFile=comicdesk.ico
UninstallDisplayIcon={app}\ComicDesk.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "deutsch"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
  GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "associate"; Description: "Comic-Dateien mit ComicDesk öffnen"; \
  GroupDescription: "Dateitypen:"

[Files]
Source: "..\dist\ComicDesk\*"; DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\ComicDesk.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\ComicDesk.exe"; \
  Tasks: desktopicon

[Registry]
; Nur unter HKCU eintragen - passend zur Installation ohne Adminrechte.
Root: HKCU; Subkey: "Software\Classes\ComicDesk.Comic"; \
  ValueType: string; ValueName: ""; ValueData: "Comic-Archiv"; \
  Flags: uninsdeletekey; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\ComicDesk.Comic\DefaultIcon"; \
  ValueType: string; ValueName: ""; ValueData: "{app}\ComicDesk.exe,0"; \
  Tasks: associate
Root: HKCU; Subkey: "Software\Classes\ComicDesk.Comic\shell\open\command"; \
  ValueType: string; ValueName: ""; \
  ValueData: """{app}\ComicDesk.exe"" ""%1"""; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\.cbz"; ValueType: string; \
  ValueName: ""; ValueData: "ComicDesk.Comic"; \
  Flags: uninsdeletevalue; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\.cbr"; ValueType: string; \
  ValueName: ""; ValueData: "ComicDesk.Comic"; \
  Flags: uninsdeletevalue; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\.cb7"; ValueType: string; \
  ValueName: ""; ValueData: "ComicDesk.Comic"; \
  Flags: uninsdeletevalue; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\.cbt"; ValueType: string; \
  ValueName: ""; ValueData: "ComicDesk.Comic"; \
  Flags: uninsdeletevalue; Tasks: associate

[Run]
Filename: "{app}\ComicDesk.exe"; \
  Description: "{cm:LaunchProgram,{#AppName}}"; \
  Flags: nowait postinstall skipifsilent
