; Inno Setup script for UniDocs (Windows).
;
; `flet build windows` only produces a portable folder (build\windows\), so this
; wraps that folder into a real installer: Start Menu entry, optional desktop
; shortcut and an entry in "Apps & features" with a working uninstaller.
;
; Built by .github/workflows/release-build.yml with:
;   ISCC.exe /DMyAppVersion=2.3.0 /DMySourceDir=<repo>/build/windows installer\unidocs.iss
; Output: installer\Output\UniDocs-<version>-windows-x86_64-setup.exe
;
; Local test build (after `flet build windows -v`):
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\unidocs.iss
;
; Docs: https://jrsoftware.org/ishelp/

#define MyAppName "UniDocs"
#define MyAppExeName "unidocs.exe"
#define MyAppPublisher "Buschauer Media"
#define MyAppURL "https://github.com/BuschauerMedia/unidocs"

; Overridden by the release workflow; the fallbacks keep a local run working.
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#ifndef MySourceDir
  #define MySourceDir "..\build\windows"
#endif

[Setup]
; Fixed ID so upgrades replace the previous install instead of stacking up.
; Never change this value.
AppId={{7C4E9F1A-2B6D-4E3A-9C58-1D0A5F7B3E24}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
VersionInfoVersion={#MyAppVersion}
; Per-user install by default: no admin prompt, lands in
; %LOCALAPPDATA%\Programs\UniDocs. An admin can still pick "all users".
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; Deliberately no ArchitecturesAllowed line: that keyword set changed in Inno
; Setup 6.3 and the release runner may ship an older version.
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=Output
OutputBaseFilename=UniDocs-{#MyAppVersion}-windows-x86_64-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; The whole Flet bundle: unidocs.exe plus its data and runtime DLLs.
Source: "{#MySourceDir}/*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
