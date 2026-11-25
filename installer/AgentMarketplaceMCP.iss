#define MyAppName "Agent Marketplace Connector"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Agent Marketplace"

[Setup]
AppId={{A6D6E75B-9F43-4C1B-8C6A-7B4A9D0C2E31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\AgentMarketplaceMCP
DisableDirPage=no
UsePreviousAppDir=no
DefaultGroupName={#MyAppName}
OutputDir=output
OutputBaseFilename=AgentMarketplaceMCP-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Uninstallable=yes

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면 바로가기 생성"; GroupDescription: "추가 작업:"; Flags: unchecked

[Dirs]
Name: "{app}\runtime"
Name: "{app}\logs"

[Files]
Source: "payload\python-3.12.10-amd64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "setup_env.ps1"; DestDir: "{tmp}"; Flags: deleteafterinstall

Source: "..\server.py"; DestDir: "{app}"
Source: "..\requirements.txt"; DestDir: "{app}"
Source: "..\.env.example"; DestDir: "{app}"; DestName: ".env.example"




Source: "..\connector\*.py"; DestDir: "{app}\connector"; Excludes: "*.backup.py,*.rollback_backup.py,*.security_backup.py"
Source: "..\agents\*"; DestDir: "{app}\agents"; Excludes: "*.pyc"; Flags: recursesubdirs createallsubdirs
Source: "..\tools\cloudflared\cloudflared.exe"; DestDir: "{app}\tools\cloudflared"



[Icons]
Name: "{group}\Agent Marketplace Connector"; Filename: "{app}\.venv\Scripts\python.exe"; Parameters: "-m connector.gui"; WorkingDir: "{app}"
Name: "{autodesktop}\Agent Marketplace Connector"; Filename: "{app}\.venv\Scripts\python.exe"; Parameters: "-m connector.gui"; WorkingDir: "{app}"; Tasks: desktopicon

[Code]
procedure ExecAndCheck(
  const FileName, Params, WorkingDir, Description: String);
var
  ResultCode: Integer;
begin
  if not Exec(
    FileName, Params, WorkingDir,
    SW_HIDE, ewWaitUntilTerminated, ResultCode
  ) then
  begin
    RaiseException(
      Description + ' 실행에 실패했습니다.' +
      Chr(13) + Chr(10) + 'Windows 오류 코드: ' + IntToStr(ResultCode)
    );
  end;

  if ResultCode <> 0 then
  begin
    RaiseException(
      Description + ' 작업이 실패했습니다.' +
      Chr(13) + Chr(10) + '종료 코드: ' + IntToStr(ResultCode) +
      Chr(13) + Chr(10) + '설치 로그: ' +
      ExpandConstant('{app}\logs\install.log')
    );
  end;
end;

procedure InstallRuntime;
var
  AppDir: String;
  PythonInstaller: String;
  PowerShellExe: String;
  SetupScript: String;
  PowerShellParams: String;
begin
  AppDir := ExpandConstant('{app}');
  PythonInstaller := ExpandConstant(
    '{tmp}\python-3.12.10-amd64.exe'
  );
  SetupScript := ExpandConstant(
    '{tmp}\setup_env.ps1'
  );
  PowerShellExe := ExpandConstant(
    '{sys}\WindowsPowerShell\v1.0\powershell.exe'
  );

  PowerShellParams :=
    '-NoProfile -ExecutionPolicy Bypass -File "' +
    SetupScript +
    '" -AppDir "' +
    AppDir +
    '" -PythonInstaller "' +
    PythonInstaller +
    '"';

  ExecAndCheck(
    PowerShellExe,
    PowerShellParams,
    AppDir,
    'Connector 초기 환경 구성'
  );
end;
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    InstallRuntime;
end;
