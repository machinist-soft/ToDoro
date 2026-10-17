; Установщик ToDoro (Inno Setup 6). Собирается скриптом tools/build_installer.py,
; который сначала делает ToDoro.exe (PyInstaller), а потом запускает этот сценарий.
; Номер версии передаётся из todoro.py (APP_VERSION): ISCC /DAppVersion=1.0

#ifndef AppVersion
  #define AppVersion "0.0"
#endif

[Setup]
; AppId — постоянный «паспорт» программы: по нему новая версия ставится поверх старой.
; Менять его нельзя.
AppId={{704F1583-0095-4838-9767-724E7112B147}
AppName=ToDoro
AppVersion={#AppVersion}
AppVerName=ToDoro {#AppVersion}
AppPublisher=Machinist
AppPublisherURL=https://github.com/machinist-soft/ToDoro
AppSupportURL=https://github.com/machinist-soft/ToDoro
AppCopyright=© 2026 Machinist
; Установка только для текущего пользователя: права администратора не нужны,
; программа ставится в %LOCALAPPDATA%\Programs\ToDoro
PrivilegesRequired=lowest
DefaultDirName={autopf}\ToDoro
DisableProgramGroupPage=yes
DisableDirPage=auto
LicenseFile=..\LICENSE
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\ToDoro.exe
UninstallDisplayName=ToDoro
OutputDir=..\dist
OutputBaseFilename=ToDoro-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Если ToDoro открыт — установщик предложит закрыть его, а после установки запустит снова
CloseApplications=yes
RestartApplications=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\build\dist\ToDoro\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; AppUserModelID — тот же, что задаёт программа: окно и ярлык на панели задач объединяются
Name: "{autoprograms}\ToDoro"; Filename: "{app}\ToDoro.exe"; AppUserModelID: "ToDoro.App"
Name: "{autodesktop}\ToDoro"; Filename: "{app}\ToDoro.exe"; AppUserModelID: "ToDoro.App"; Tasks: desktopicon

[Run]
; Без skipifsilent: при обновлении из программы (тихая установка) новая версия запускается сама
Filename: "{app}\ToDoro.exe"; Description: "{cm:LaunchProgram,ToDoro}"; Flags: nowait postinstall

; Задачи (%APPDATA%\ToDoro\todoro.db) при удалении программы НЕ удаляются.

[UninstallRun]
; Значок ToDoro в трее держит ToDoro.exe открытым — сначала закрываем его
Filename: "{app}\ToDoro.exe"; Parameters: "--tray-quit"; RunOnceId: "TrayQuit"; Flags: runhidden waituntilterminated

[Code]
// Автозапуск значка в трее записывает сама программа; при удалении программы убираем его
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'ToDoro');
end;
