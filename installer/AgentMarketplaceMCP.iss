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
ArchitecturesInstallIn64BitMode=x64compatible
Uninstallable=yes

[Languages]
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

Source: "..\connector\agent_manager.py"; DestDir: "{app}\connector"
Source: "..\connector\cli.py"; DestDir: "{app}\connector"
Source: "..\connector\gui.py"; DestDir: "{app}\connector"
Source: "..\connector\integrity.py"; DestDir: "{app}\connector"
Source: "..\connector\mcp_client.py"; DestDir: "{app}\connector"
Source: "..\connector\security.py"; DestDir: "{app}\connector"
Source: "..\connector\server_manager.py"; DestDir: "{app}\connector"

Source: "..\agents\*"; DestDir: "{app}\agents"; Flags: recursesubdirs createallsubdirs
Source: "..\tools\cloudflared\cloudflared.exe"; DestDir: "{app}\tools\cloudflared"

[Run]
Filename: "{tmp}\python-3.12.10-amd64.exe"; Parameters: "/quiet InstallAllUsers=0 TargetDir=""{app}\python"" Include_launcher=0 Include_test=0 PrependPath=0"; StatusMsg: "Python 설치 중..."; Flags: waituntilterminated
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{tmp}\setup_env.ps1"" -AppDir ""{app}"""; StatusMsg: "Agent Marketplace 구성 중..."; Flags: waituntilterminated

[Icons]
Name: "{group}\Agent Marketplace Connector"; Filename: "{app}\.venv\Scripts\python.exe"; Parameters: "-m connector.gui"; WorkingDir: "{app}"
Name: "{autodesktop}\Agent Marketplace Connector"; Filename: "{app}\.venv\Scripts\python.exe"; Parameters: "-m connector.gui"; WorkingDir: "{app}"; Tasks: desktopicon
