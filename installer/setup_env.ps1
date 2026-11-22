param(
    [Parameter(Mandatory=$true)]
    [string]$AppDir,

    [Parameter(Mandatory=$true)]
    [string]$PythonInstaller
)

$ErrorActionPreference = "Stop"

$AppDir = [System.IO.Path]::GetFullPath($AppDir)

$LogDir = Join-Path $AppDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$LogPath = Join-Path $LogDir "install.log"
Start-Transcript -Path $LogPath -Append

function Get-PythonInfo {
    param([string]$Executable)

    if (!(Test-Path -LiteralPath $Executable -PathType Leaf)) {
        return $null
    }

    $result = & $Executable -c "import json, struct, sys; print(json.dumps({'version': str(sys.version_info.major)+'.'+str(sys.version_info.minor), 'bits': struct.calcsize('P')*8, 'is_venv': sys.prefix != sys.base_prefix}))" 2>$null

    if ($LASTEXITCODE -ne 0 -or !$result) {
        return $null
    }

    try {
        return (($result -join "`n") | ConvertFrom-Json)
    }
    catch {
        return $null
    }
}

try {
    Write-Host "=== Agent Marketplace 설치 초기화 ==="

    if (![Environment]::Is64BitOperatingSystem) {
        throw "64비트 Windows만 지원합니다."
    }

    $Candidates = [System.Collections.Generic.List[string]]::new()

    [void]$Candidates.Add(
        (Join-Path $AppDir "python\python.exe")
    )

    $RegistryPaths = @(
        "Registry::HKEY_CURRENT_USER\Software\Python\PythonCore\3.12\InstallPath",
        "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Python\PythonCore\3.12\InstallPath"
    )

    foreach ($RegistryPath in $RegistryPaths) {
        try {
            $RegistryKey = Get-Item -LiteralPath $RegistryPath -ErrorAction Stop

            $RegisteredExe = [string]$RegistryKey.GetValue("ExecutablePath")
            $RegisteredDir = [string]$RegistryKey.GetValue("")

            if ($RegisteredExe) {
                [void]$Candidates.Add($RegisteredExe)
            }

            if ($RegisteredDir) {
                [void]$Candidates.Add(
                    (Join-Path $RegisteredDir "python.exe")
                )
            }
        }
        catch {
            # 등록 정보가 없으면 다음 경로 확인
        }
    }

    [void]$Candidates.Add(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe")
    )

    [void]$Candidates.Add(
        (Join-Path $env:ProgramFiles "Python312\python.exe")
    )

    $Candidates = @($Candidates | Select-Object -Unique)
    $Python = $null

    foreach ($Candidate in $Candidates) {
        if (!(Test-Path -LiteralPath $Candidate -PathType Leaf)) {
            continue
        }

        $Info = Get-PythonInfo $Candidate

        if (
            $null -ne $Info -and
            $Info.version -eq "3.12" -and
            $Info.bits -eq 64 -and
            !$Info.is_venv
        ) {
            $Python = $Candidate
            Write-Host "사용할 Python: $Python"
            Write-Host "Python 버전: $($Info.version)"
            Write-Host "아키텍처: $($Info.bits)-bit"
            break
        }
    }

    if (!$Python) {
        Write-Host "호환 Python이 없습니다. 번들 Python 설치를 시작합니다."

        if (!(Test-Path -LiteralPath $PythonInstaller -PathType Leaf)) {
            throw "번들 Python 설치 파일을 찾을 수 없습니다."
        }

        $BundledPythonDir = Join-Path $AppDir "python"
        $PythonLog = Join-Path $LogDir "python-install.log"

        New-Item -ItemType Directory -Force -Path $BundledPythonDir | Out-Null

        $PythonParams = '/quiet InstallAllUsers=0 TargetDir="' +
            $BundledPythonDir +
            '" Include_launcher=0 Include_test=0 PrependPath=0 /log "' +
            $PythonLog +
            '"'

        $Process = Start-Process `
            -FilePath $PythonInstaller `
            -ArgumentList $PythonParams `
            -Wait `
            -PassThru

        if ($Process.ExitCode -ne 0) {
            throw "번들 Python 설치 실패. 종료 코드: $($Process.ExitCode). 로그: $PythonLog"
        }

        $Python = Join-Path $BundledPythonDir "python.exe"
        $Info = Get-PythonInfo $Python

        if (
            $null -eq $Info -or
            $Info.version -ne "3.12" -or
            $Info.bits -ne 64 -or
            $Info.is_venv
        ) {
            throw "번들 Python 설치 검증 실패. 로그: $PythonLog"
        }

        Write-Host "번들 Python 설치 및 검증 성공"
    }
    else {
        Write-Host "기존 Python 설치 재사용"
    }

    $VenvDir = Join-Path $AppDir ".venv"
    $VenvPython = Join-Path $VenvDir "Scripts\python.exe"

    if (!(Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
        Write-Host "가상환경 생성 중..."

        & $Python -m venv $VenvDir

        if ($LASTEXITCODE -ne 0) {
            throw "Python 가상환경 생성 실패"
        }
    }

    if (!(Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
        throw "가상환경 Python 실행 파일이 없습니다."
    }

    $VenvInfo = Get-PythonInfo $VenvPython

    if (
        $null -eq $VenvInfo -or
        $VenvInfo.version -ne "3.12" -or
        $VenvInfo.bits -ne 64 -or
        !$VenvInfo.is_venv
    ) {
        throw "가상환경 검증 실패"
    }

    Write-Host "가상환경 확인 완료"

    Write-Host "필수 패키지 설치 중..."

    & $VenvPython -m pip install --disable-pip-version-check -r (
        Join-Path $AppDir "requirements.txt"
    )

    if ($LASTEXITCODE -ne 0) {
        throw "필수 패키지 설치 실패"
    }

    $EnvPath = Join-Path $AppDir ".env"

    if (!(Test-Path $EnvPath)) {
        $Bytes = New-Object byte[] 32
        $Rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()

        try {
            $Rng.GetBytes($Bytes)
        }
        finally {
            $Rng.Dispose()
        }

        $Token = [Convert]::ToBase64String($Bytes).TrimEnd('=').Replace('+','-').Replace('/','_')

        $EnvContent = @"
MCP_AUTH_TOKEN=$Token
MCP_ALLOWED_HOSTS=
CLAUDE_TEST_TOKEN=
"@

        $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

        [System.IO.File]::WriteAllText(
            $EnvPath,
            $EnvContent,
            $Utf8NoBom
        )

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