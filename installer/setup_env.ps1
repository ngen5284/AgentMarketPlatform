param(
    [Parameter(Mandatory=$true)]
    [string]$AppDir
)

$ErrorActionPreference = "Stop"

$AppDir = [System.IO.Path]::GetFullPath($AppDir)
$LogDir = Join-Path $AppDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$LogPath = Join-Path $LogDir "install.log"
Start-Transcript -Path $LogPath -Append

try {
    Write-Host "=== Agent Marketplace 설치 초기화 ==="

    $VenvPython = Join-Path $AppDir ".venv\Scripts\python.exe"

    $Candidates = @(
        (Join-Path $AppDir "python\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        (Join-Path $env:ProgramFiles "Python312\python.exe")
    )

    $Python = $null

    foreach ($Candidate in $Candidates) {
        if (Test-Path $Candidate) {
            $Version = & $Candidate --version 2>&1
            if ($Version -match "^Python 3\.12\.") {
                $Python = $Candidate
                Write-Host "사용할 Python: $Python"
                Write-Host "버전: $Version"
                break
            }
        }
    }

    if (-not $Python) {
        throw "사용 가능한 Python 3.12를 찾지 못했습니다."
    }

    if (-not (Test-Path $VenvPython)) {
        Write-Host "가상환경 생성 중..."
        & $Python -m venv (Join-Path $AppDir ".venv")

        if ($LASTEXITCODE -ne 0) {
            throw "가상환경 생성 실패"
        }
    }

    if (-not (Test-Path $VenvPython)) {
        throw "가상환경 Python 실행 파일을 찾을 수 없습니다."
    }

    Write-Host "필수 패키지 설치 중..."
    & $VenvPython -m pip install --disable-pip-version-check -r (Join-Path $AppDir "requirements.txt")

    if ($LASTEXITCODE -ne 0) {
        throw "필수 패키지 설치 실패"
    }

    $EnvPath = Join-Path $AppDir ".env"

    if (-not (Test-Path $EnvPath)) {
        $Bytes = New-Object byte[] 32
        $Rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        $Rng.GetBytes($Bytes)
        $Rng.Dispose()

        $Token = [Convert]::ToBase64String($Bytes).TrimEnd('=').Replace('+','-').Replace('/','_')

        $EnvContent = @"
MCP_AUTH_TOKEN=$Token
MCP_ALLOWED_HOSTS=
CLAUDE_TEST_TOKEN=
"@

        $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($EnvPath, $EnvContent, $Utf8NoBom)
        Write-Host "인증 토큰 생성 완료"
    }
    else {
        Write-Host "기존 환경 설정 유지"
    }

    Write-Host "설치 초기화 성공"
}
catch {
    Write-Host "설치 오류: $($_.Exception.Message)"
    exit 1
}
finally {
    Stop-Transcript
}