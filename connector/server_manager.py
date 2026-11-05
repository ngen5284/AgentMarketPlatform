import json
import os
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
PYTHON_EXE = BASE_DIR / ".venv" / "Scripts" / "python.exe"
SERVER_SCRIPT = BASE_DIR / "server.py"

RUNTIME_DIR = BASE_DIR / "runtime"
PID_FILE = RUNTIME_DIR / "server.pid.json"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "mcp_server.log"  # Legacy log path; retained for backward compatibility.
MCP_LOG_DIR = LOG_DIR / "MCP"


def _new_session_log_path(prefix):
    """Create a unique log path for one process run without overwriting history."""
    MCP_LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return MCP_LOG_DIR / f"{prefix}_{timestamp}.log"


def get_latest_log_file(prefix="mcp_server"):
    """Return the newest session log, falling back to the legacy fixed log."""
    search_dir = MCP_LOG_DIR if prefix == "mcp_server" else LOG_DIR
    candidates = list(search_dir.glob(f"{prefix}_*.log")) if search_dir.exists() else []
    if candidates:
        return max(candidates, key=lambda item: item.stat().st_mtime_ns)
    if prefix == "mcp_server" and LOG_FILE.is_file():
        return LOG_FILE
    return LOG_DIR / f"{prefix}.log"


HOST = "127.0.0.1"
PORT = 8000


def _port_is_open():
    try:
        with socket.create_connection((HOST, PORT), timeout=1):
            return True
    except OSError:
        return False


def _read_pid_data():
    if not PID_FILE.is_file():
        return None

    try:
        return json.loads(PID_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _get_process_info(pid):
    if os.name != "nt":
        return None

    command = (
        f"$p = Get-CimInstance Win32_Process "
        f"-Filter 'ProcessId = {int(pid)}' -ErrorAction SilentlyContinue; "
        f"if ($p) {{ $p | Select-Object ProcessId, ExecutablePath, "
        f"CommandLine | ConvertTo-Json -Compress }}"
    )

    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        if result.returncode != 0 or not result.stdout.strip():
            return None

        return json.loads(result.stdout)

    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def _is_managed_process(data):
    if not data:
        return False

    info = _get_process_info(data.get("pid", 0))
    if not info:
        return False

    command_line = info.get("CommandLine") or ""
    expected_script = str(SERVER_SCRIPT.resolve()).lower()

    normalized_command = command_line.replace("/", "\\").lower()

    return (
        expected_script in normalized_command
        and "streamable-http" in normalized_command
        and str(BASE_DIR).lower() in normalized_command
    )


def get_process_status():
    data = _read_pid_data()
    managed = _is_managed_process(data)

    port_open = _port_is_open()

    if managed and port_open:
        return {
            "success": True,
            "running": True,
            "managed": True,
            "pid": data["pid"],
            "message": "Connector가 시작한 MCP 서버가 실행 중입니다.",
        }

    if port_open:
        return {
            "success": True,
            "running": True,
            "managed": False,
            "pid": None,
            "message": "MCP 서버가 실행 중이지만 Connector 관리 대상은 아닙니다.",
        }

    return {
        "success": True,
        "running": False,
        "managed": False,
        "pid": None,
        "message": "MCP 서버가 실행 중이지 않습니다.",
    }


def start_server():
    if os.name != "nt":
        return {
            "success": False,
            "message": "현재 서버 관리 기능은 Windows 환경만 지원합니다.",
        }

    if not PYTHON_EXE.is_file() or not SERVER_SCRIPT.is_file():
        return {
            "success": False,
            "message": "Python 가상환경 또는 server.py를 찾을 수 없습니다.",
        }

    if _port_is_open():
        return {
            "success": False,
            "message": "8000번 포트가 이미 사용 중입니다. 기존 서버를 확인하세요.",
        }

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if PID_FILE.exists():
        old_data = _read_pid_data()

        if old_data and _is_managed_process(old_data):
            return {
                "success": False,
                "message": "기존 Connector 관리 서버가 이미 실행 중입니다.",
                "pid": old_data.get("pid"),
            }

        if old_data and _get_process_info(old_data.get("pid", 0)):
            return {
                "success": False,
                "message": "PID 파일의 프로세스 소유권을 확인할 수 없습니다. 자동 삭제하지 않았습니다.",
            }

        PID_FILE.unlink(missing_ok=True)

    log_handle = None
    session_log_file = _new_session_log_path("mcp_server")

    try:
        log_handle = open(session_log_file, "a", encoding="utf-8")
        log_handle.write(
            f"\n--- MCP server start {datetime.now().isoformat(timespec='seconds')} ---\n"
        )
        log_handle.flush()

        process = subprocess.Popen(
            [
                str(PYTHON_EXE),
                "-u",
                str(SERVER_SCRIPT),
                "streamable-http",
            ],
            cwd=str(BASE_DIR),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

        data = {
            "pid": process.pid,
            "project_dir": str(BASE_DIR),
            "server_script": str(SERVER_SCRIPT),
            "started_at": datetime.now().isoformat(),
            "log_file": str(session_log_file),
        }

        temp_file = PID_FILE.with_suffix(".tmp")
        temp_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_file.replace(PID_FILE)

        for _ in range(20):
            if process.poll() is not None:
                PID_FILE.unlink(missing_ok=True)
                return {
                    "success": False,
                    "message": "MCP 서버 프로세스가 시작 직후 종료됐습니다. 로그를 확인하세요.",
                    "log_file": str(session_log_file),
                }

            if _port_is_open():
                return {
                    "success": True,
                    "pid": process.pid,
                    "message": "MCP 서버가 시작됐습니다.",
                    "log_file": str(session_log_file),
                }

            time.sleep(0.5)

        return {
            "success": False,
            "pid": process.pid,
            "message": "서버 시작 확인 시간이 초과됐습니다. 프로세스와 로그를 확인하세요.",
            "log_file": str(session_log_file),
        }

    except Exception as exc:
        return {
            "success": False,
            "message": f"서버 시작 실패: {type(exc).__name__}: {exc}",
        }

    finally:
        if log_handle is not None:
            log_handle.close()


def stop_server():
    if os.name != "nt":
        return {
            "success": False,
            "message": "현재 서버 관리 기능은 Windows 환경만 지원합니다.",
        }

    data = _read_pid_data()

    if not data:
        return {
            "success": False,
            "message": "Connector가 관리하는 PID 파일이 없습니다. 기존 서버는 종료하지 않았습니다.",
        }

    if not _is_managed_process(data):
        return {
            "success": False,
            "message": "프로세스 소유권을 확인할 수 없습니다. 안전을 위해 종료하지 않았습니다.",
        }

    pid = int(data["pid"])

    try:
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "message": result.stderr.strip() or result.stdout.strip() or "프로세스 종료에 실패했습니다.",
            }

        PID_FILE.unlink(missing_ok=True)

        return {
            "success": True,
            "pid": pid,
            "message": "Connector가 시작한 MCP 서버를 종료했습니다.",
        }

    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "success": False,
            "message": f"서버 종료 실패: {type(exc).__name__}: {exc}",
        }
