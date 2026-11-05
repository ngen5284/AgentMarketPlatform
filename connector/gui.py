import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values, set_key
from PySide6.QtCore import (
    Qt, QThread, Signal, QUrl, QPropertyAnimation, QEasingCurve, QPointF
)
from PySide6.QtGui import QDesktopServices, QTextCursor, QColor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QFileDialog,
    QGraphicsDropShadowEffect,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,

    QScrollArea,)

from connector.agent_manager import install_agent, list_agents, remove_agent
from connector.integrity import verify_package_integrity
from connector.mcp_client import check_server_status, refresh_server_agents
from connector.security import verify_package_security
from connector.server_manager import (
    BASE_DIR,
    LOG_DIR,
    PYTHON_EXE,
    SERVER_SCRIPT,
    get_process_status,
    get_latest_log_file,
    start_server,
    stop_server,
)


ENV_PATH = BASE_DIR / ".env"
MCP_URL = "http://127.0.0.1:8000/mcp"
MCP_ORIGIN = "http://127.0.0.1:8000"
CLOUDFLARED_EXE = BASE_DIR / "tools" / "cloudflared" / "cloudflared.exe"
RUNTIME_DIR = BASE_DIR / "runtime"
TUNNEL_PID_FILE = RUNTIME_DIR / "cloudflared.pid.json"
TUNNEL_LOG_FILE = LOG_DIR / "cloudflared.log"  # Legacy fixed log path.
TUNNEL_LOG_DIR = LOG_DIR / "Cloudflare"
TUNNEL_URL_PATTERN = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")


class AnimatedButton(QPushButton):
    """Shared subtle hover/press animation for every button in the GUI."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(0)
        self._shadow.setOffset(QPointF(0, 0))
        self._shadow.setColor(QColor(52, 64, 84, 65))
        self.setGraphicsEffect(self._shadow)

        self._blur_animation = QPropertyAnimation(
            self._shadow, b"blurRadius", self
        )
        self._offset_animation = QPropertyAnimation(
            self._shadow, b"offset", self
        )
        for animation in (self._blur_animation, self._offset_animation):
            animation.setDuration(135)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _animate_feedback(self, blur, offset_y):
        if not self.isEnabled():
            return

        self._blur_animation.stop()
        self._blur_animation.setStartValue(self._shadow.blurRadius())
        self._blur_animation.setEndValue(float(blur))
        self._blur_animation.start()

        self._offset_animation.stop()
        self._offset_animation.setStartValue(self._shadow.offset())
        self._offset_animation.setEndValue(QPointF(0, float(offset_y)))
        self._offset_animation.start()

    def enterEvent(self, event):
        self._animate_feedback(9, 2)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_feedback(0, 0)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._animate_feedback(3, 1)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.underMouse():
            self._animate_feedback(9, 2)
        else:
            self._animate_feedback(0, 0)


# Keep the existing button construction code while applying one shared widget class.
QPushButton = AnimatedButton


def get_latest_tunnel_log_file():
    candidates = (
        list(TUNNEL_LOG_DIR.glob("cloudflared_*.log"))
        if TUNNEL_LOG_DIR.exists()
        else []
    )
    if candidates:
        return max(candidates, key=lambda item: item.stat().st_mtime_ns)
    return TUNNEL_LOG_FILE


def read_auth_token():
    """Read the token from .env first, then fall back to the process environment."""
    values = dotenv_values(str(ENV_PATH)) if ENV_PATH.is_file() else {}
    token = values.get("MCP_AUTH_TOKEN") or os.environ.get("MCP_AUTH_TOKEN", "")
    return token.strip() if isinstance(token, str) else ""


def read_claude_token():
    """Read CLAUDE_TEST_TOKEN from .env or process environment."""
    values = dotenv_values(str(ENV_PATH)) if ENV_PATH.is_file() else {}
    token = values.get("CLAUDE_TEST_TOKEN") or os.environ.get("CLAUDE_TEST_TOKEN", "")
    return token.strip() if isinstance(token, str) else ""

def save_claude_token(token):
    token = token.strip()
    if not token:
        raise ValueError("Claude 연결 토큰은 비워 둘 수 없습니다.")

    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    set_key(str(ENV_PATH), "CLAUDE_TEST_TOKEN", token, quote_mode="always")
    os.environ["CLAUDE_TEST_TOKEN"] = token


def save_auth_token(token):
    token = token.strip()
    if not token:
        raise ValueError("인증 토큰은 비워 둘 수 없습니다.")
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    set_key(str(ENV_PATH), "MCP_AUTH_TOKEN", token, quote_mode="always")
    os.environ["MCP_AUTH_TOKEN"] = token


def save_allowed_tunnel_host(public_url):
    """Persist only a Cloudflare Quick Tunnel hostname for the MCP host allowlist."""
    parsed = urlparse(public_url)
    host = (parsed.hostname or "").lower()

    if not re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.trycloudflare\.com",
        host,
    ):
        raise ValueError("유효한 trycloudflare.com 외부 주소가 아닙니다.")

    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    set_key(str(ENV_PATH), "MCP_ALLOWED_HOSTS", host, quote_mode="never")
    os.environ["MCP_ALLOWED_HOSTS"] = host
    return host


def read_tunnel_url(log_file=None):
    if log_file is None:
        pid_data = read_tunnel_pid_data()
        stored_path = pid_data.get("log_file") if pid_data else None
        log_file = Path(stored_path) if stored_path else get_latest_tunnel_log_file()
    else:
        log_file = Path(log_file)

    if not log_file.is_file():
        return ""
    try:
        text = log_file.read_text(encoding="utf-8", errors="replace")[-30000:]
    except OSError:
        return ""
    matches = TUNNEL_URL_PATTERN.findall(text)
    return matches[-1] if matches else ""

def read_tunnel_pid_data():
    if not TUNNEL_PID_FILE.is_file():
        return None
    try:
        data = json.loads(TUNNEL_PID_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def get_windows_process_info(pid):
    if os.name != "nt" or not pid:
        return None
    command = (
        f"$p = Get-CimInstance Win32_Process -Filter 'ProcessId = {int(pid)}' "
        "-ErrorAction SilentlyContinue; "
        "if ($p) { $p | Select-Object ProcessId, ExecutablePath, CommandLine "
        "| ConvertTo-Json -Compress }"
    )
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=6,
            check=False,
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            return None
        result = json.loads(completed.stdout)
        return result if isinstance(result, dict) else None
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def is_managed_tunnel_process(data):
    """Confirm the PID belongs to this project's cloudflared Quick Tunnel.

    Do not replace forward slashes in CommandLine: doing so also corrupts
    the http:// URL argument and makes the origin comparison fail.
    """
    if not data:
        return False

    actual_executable = os.path.normcase(
        os.path.abspath(str(data.get("ExecutablePath") or ""))
    )
    expected_executable = os.path.normcase(
        os.path.abspath(str(CLOUDFLARED_EXE))
    )
    command_line = str(data.get("CommandLine") or "").casefold()

    executable_matches = actual_executable == expected_executable
    command_matches = (
        " tunnel " in f" {command_line} "
        and "--url" in command_line
        and MCP_ORIGIN.casefold() in command_line
    )

    return executable_matches and command_matches


def get_tunnel_status():
    data = read_tunnel_pid_data()
    if not data or not data.get("pid"):
        return {
            "success": True,
            "running": False,
            "url": "",
            "message": "Cloudflare Tunnel이 실행 중이지 않습니다.",
        }

    process_info = get_windows_process_info(data.get("pid"))
    if not process_info:
        TUNNEL_PID_FILE.unlink(missing_ok=True)
        return {
            "success": True,
            "running": False,
            "url": "",
            "message": "종료된 Tunnel 프로세스 기록을 정리했습니다.",
        }

    if not is_managed_tunnel_process(process_info):
        return {
            "success": False,
            "running": False,
            "url": "",
            "message": "PID 파일의 프로세스가 Connector가 시작한 Cloudflare Tunnel인지 확인할 수 없습니다.",
        }

    log_path = data.get("log_file")
    base_url = read_tunnel_url(log_path) if log_path else read_tunnel_url(TUNNEL_LOG_FILE)
    return {
        "success": True,
        "running": True,
        "url": f"{base_url}/mcp" if base_url else "",
        "message": "Cloudflare Tunnel 프로세스가 실행 중입니다." if base_url else "Tunnel은 실행 중이며 외부 주소를 확인하고 있습니다.",
        "pid": data.get("pid"),
    }


def start_cloudflare_tunnel(check_mcp=True):
    if os.name != "nt":
        return {"success": False, "message": "Cloudflare Tunnel 관리는 Windows 환경을 기준으로 구현되어 있습니다."}

    current = get_tunnel_status()
    if not current.get("success"):
        return current
    if current.get("running"):
        return {
            "success": True,
            "already_running": True,
            "url": current.get("url", ""),
            "message": "Cloudflare Tunnel이 이미 실행 중입니다.",
        }

    if not CLOUDFLARED_EXE.is_file():
        return {
            "success": False,
            "message": f"cloudflared 실행 파일을 찾을 수 없습니다: {CLOUDFLARED_EXE}",
        }

    if check_mcp:
        mcp_result = check_server_status()
        if not mcp_result.get("success"):
            return {
                "success": False,
                "message": "MCP 서버 연결이 확인되지 않아 Tunnel을 시작하지 않았습니다. MCP 서버와 인증 토큰을 먼저 확인하세요.",
                "detail": mcp_result.get("message", ""),
            }

    TUNNEL_LOG_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    # Keep every run's output in its own file; never erase previous diagnostics.
    session_stamp = time.strftime("%Y%m%d_%H%M%S") + f"_{time.time_ns() % 1_000_000_000:09d}"
    session_log_file = TUNNEL_LOG_DIR / f"cloudflared_{session_stamp}.log"

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        with session_log_file.open("a", encoding="utf-8") as log_handle:
            log_handle.write(f"\n--- Tunnel start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            log_handle.flush()
            process = subprocess.Popen(
                [str(CLOUDFLARED_EXE), "tunnel", "--url", MCP_ORIGIN],
                cwd=str(BASE_DIR),
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )

        temp_file = TUNNEL_PID_FILE.with_suffix(".tmp")
        temp_file.write_text(
            json.dumps({"pid": process.pid, "started_at": time.strftime("%Y-%m-%d %H:%M:%S"), "log_file": str(session_log_file)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_file.replace(TUNNEL_PID_FILE)

        for _ in range(40):
            if process.poll() is not None:
                TUNNEL_PID_FILE.unlink(missing_ok=True)
                return {
                    "success": False,
                    "message": "Cloudflare Tunnel 프로세스가 시작 직후 종료됐습니다.",
                    "log_file": str(session_log_file),
                }
            base_url = read_tunnel_url(session_log_file)
            if base_url:
                return {
                    "success": True,
                    "url": f"{base_url}/mcp",
                    "pid": process.pid,
                    "message": "Cloudflare Tunnel이 시작되고 외부 주소가 생성됐습니다.",
                }
            time.sleep(0.5)

        return {
            "success": True,
            "url": "",
            "pid": process.pid,
            "message": "Tunnel 프로세스는 실행 중이나 외부 주소 확인이 지연되고 있습니다. 로그를 확인하세요.",
            "log_file": str(session_log_file),
        }
    except Exception as exc:
        return {"success": False, "message": f"Tunnel 시작 실패: {type(exc).__name__}: {exc}"}


def start_tunnel_and_apply_host():
    """Start the Tunnel independently and apply its hostname to MCP safely."""
    server_before = get_process_status()
    if server_before.get("running") and not server_before.get("managed"):
        # It is safe to run cloudflared, but the already-running unmanaged MCP
        # cannot be restarted safely by this Connector.
        unmanaged_server = True
    else:
        unmanaged_server = False

    tunnel_result = start_cloudflare_tunnel(check_mcp=False)
    if not tunnel_result.get("success"):
        return tunnel_result

    public_url = tunnel_result.get("url", "")
    if not public_url:
        return {
            "success": False,
            "running": True,
            "message": (
                "Cloudflare Tunnel 프로세스는 실행 중이지만 외부 주소를 아직 "
                "확인하지 못했습니다. Tunnel 로그를 확인하세요."
            ),
            "tunnel": tunnel_result,
        }

    values = dotenv_values(str(ENV_PATH)) if ENV_PATH.is_file() else {}
    old_hosts = {
        item.strip().lower()
        for item in str(values.get("MCP_ALLOWED_HOSTS") or "").split(",")
        if item.strip()
    }
    new_host = save_allowed_tunnel_host(public_url)
    host_changed = new_host not in old_hosts

    server_after = get_process_status()
    restart_result = None
    mcp_result = None

    # MCP 서버가 실행 중이지 않으면 Connector가 직접 시작
    if not server_after.get("running"):
        restart_result = start_server()

        if not restart_result.get("success"):
            return {
                "success": False,
                "running": True,
                "url": public_url,
                "message": "Cloudflare Tunnel은 실행됐지만 MCP 서버 시작에 실패했습니다.",
                "detail": restart_result,
                "tunnel": tunnel_result,
            }

        for _ in range(16):
            mcp_result = check_server_status()
            if mcp_result.get("success"):
                break
            time.sleep(0.5)

        if not mcp_result or not mcp_result.get("success"):
            return {
                "success": False,
                "running": True,
                "url": public_url,
                "message": "MCP 서버를 시작했지만 로컬 연결 확인에 실패했습니다.",
                "detail": mcp_result,
                "tunnel": tunnel_result,
            }

    if host_changed and server_after.get("running") and server_after.get("managed"):
        stopped = stop_server()
        if not stopped.get("success"):
            return {
                "success": False,
                "running": True,
                "url": public_url,
                "message": "새 Tunnel 주소를 허용 목록에 저장했지만 MCP 서버 재시작에 실패했습니다.",
                "detail": stopped,
                "tunnel": tunnel_result,
            }

        restart_result = start_server()
        if not restart_result.get("success"):
            return {
                "success": False,
                "running": True,
                "url": public_url,
                "message": "Tunnel은 실행 중이지만 새 허용 주소를 적용한 MCP 서버 재시작에 실패했습니다.",
                "detail": restart_result,
                "tunnel": tunnel_result,
            }

        for _ in range(12):
            mcp_result = check_server_status()
            if mcp_result.get("success"):
                break
            time.sleep(0.5)

        if not mcp_result or not mcp_result.get("success"):
            return {
                "success": False,
                "running": True,
                "url": public_url,
                "message": "MCP 서버를 재시작했지만 로컬 연결 확인에 실패했습니다.",
                "detail": mcp_result,
                "tunnel": tunnel_result,
            }

    elif host_changed and unmanaged_server:
        return {
            "success": True,
            "running": True,
            "url": public_url,
            "message": (
                "Tunnel은 실행됐고 새 주소도 저장했습니다. 다만 MCP 서버는 "
                "Connector가 관리하지 않는 프로세스이므로 자동 재시작하지 않았습니다. "
                "외부 접속을 적용하려면 해당 MCP 서버를 직접 재시작해야 합니다."
            ),
            "host": new_host,
            "tunnel": tunnel_result,
        }

    return {
        "success": True,
        "running": True,
        "url": public_url,
        "host": new_host,
        "host_changed": host_changed,
        "message": (
            "Cloudflare Tunnel이 실행됐고 새 외부 주소가 MCP 허용 목록에 반영됐습니다."
            if host_changed
            else "Cloudflare Tunnel이 실행 중이며 MCP 허용 주소도 최신 상태입니다."
        ),
        "restart": restart_result,
        "mcp": mcp_result,
        "tunnel": tunnel_result,
    }


def stop_cloudflare_tunnel():
    data = read_tunnel_pid_data()
    if not data or not data.get("pid"):
        return {"success": True, "message": "관리 중인 Cloudflare Tunnel이 없습니다."}

    pid = int(data["pid"])
    process_info = get_windows_process_info(pid)
    if not process_info:
        TUNNEL_PID_FILE.unlink(missing_ok=True)
        return {"success": True, "message": "이미 종료된 Tunnel 기록을 정리했습니다."}

    if not is_managed_tunnel_process(process_info):
        return {
            "success": False,
            "message": "프로세스 소유권을 확인할 수 없어 종료하지 않았습니다.",
        }

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
                "message": result.stderr.strip() or result.stdout.strip() or "Tunnel 종료에 실패했습니다.",
            }
        TUNNEL_PID_FILE.unlink(missing_ok=True)
        return {"success": True, "message": "Cloudflare Tunnel을 종료했습니다."}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"success": False, "message": f"Tunnel 종료 실패: {type(exc).__name__}: {exc}"}


class StatusWorker(QThread):
    result_ready = Signal(dict)
    progress = Signal(str, int)

    def run(self):
        results = {}
        steps = (
            ("server", "로컬 MCP 서버 상태 확인", get_process_status),
            ("mcp", "MCP 연결 및 도구 목록 확인", check_server_status),
            ("tunnel", "Cloudflare Tunnel 상태 확인", get_tunnel_status),
            ("agents", "설치된 에이전트 목록 확인", list_agents),
        )

        total = len(steps)
        for index, (key, label, function) in enumerate(steps):
            self.progress.emit(label, int(index * 100 / total))
            try:
                results[key] = function()
            except Exception as exc:
                results[key] = {
                    "success": False,
                    "error": str(exc),
                    "message": f"{type(exc).__name__}: {exc}",
                }
            self.progress.emit(f"{label} 완료", int((index + 1) * 100 / total))

        self.progress.emit("상태 조회 완료", 100)
        self.result_ready.emit(results)


class AgentWorker(QThread):
    result_ready = Signal(dict)

    def __init__(self, action, value=None):
        super().__init__()
        self.action = action
        self.value = value

    def run(self):
        try:
            if self.action == "list":
                operation = {"success": True, "message": "에이전트 목록을 조회했습니다."}
            elif self.action == "install":
                installed = install_agent(self.value)
                operation = {
                    "success": True,
                    "message": "에이전트를 가져왔습니다.",
                    "detail": installed,
                }
                refresh = installed.get("refresh", {})
                if not refresh.get("success"):
                    operation["message"] += " 단, MCP 서버 도구 갱신은 실패했습니다: " + refresh.get("message", "")
            elif self.action == "remove":
                removed = remove_agent(self.value)
                operation = {
                    "success": bool(removed.get("removed")),
                    "message": "에이전트를 삭제했습니다." if removed.get("removed") else "에이전트 삭제에 실패했습니다.",
                    "detail": removed,
                }
                refresh = removed.get("refresh", {})
                if not refresh.get("success"):
                    operation["message"] += " 단, MCP 서버 도구 갱신은 실패했습니다: " + refresh.get("message", "")
            else:
                raise ValueError(f"지원하지 않는 작업입니다: {self.action}")
            agents = list_agents()
            self.result_ready.emit({"operation": operation, "agents": agents})
        except Exception as exc:
            try:
                agents = list_agents()
            except Exception:
                agents = []
            self.result_ready.emit({
                "operation": {"success": False, "message": f"{type(exc).__name__}: {exc}"},
                "agents": agents,
            })


class OperationWorker(QThread):
    result_ready = Signal(dict)

    def __init__(self, action, value=None):
        super().__init__()
        self.action = action
        self.value = value

    def run(self):
        try:
            if self.action == "start_server":
                result = start_server()
            elif self.action == "stop_server":
                result = stop_server()
            elif self.action == "process_status":
                result = get_process_status()
            elif self.action == "mcp_status":
                result = check_server_status()
            elif self.action == "refresh_tools":
                result = refresh_server_agents()
            elif self.action == "security":
                result = verify_package_security(self.value)
            elif self.action == "integrity":
                result = verify_package_integrity(self.value)
            elif self.action == "tunnel_start":
                result = start_tunnel_and_apply_host()
            elif self.action == "tunnel_stop":
                result = stop_cloudflare_tunnel()
            elif self.action == "tunnel_status":
                result = get_tunnel_status()
            elif self.action == "logs":
                current_log = get_latest_log_file("mcp_server")
                if current_log.is_file():
                    lines = current_log.read_text(encoding="utf-8", errors="replace").splitlines()
                    result = {"success": True, "text": "\n".join(lines[-500:]) or "로그 파일이 비어 있습니다."}
                else:
                    result = {"success": True, "text": "아직 로그 파일이 없습니다."}
            elif self.action == "tunnel_logs":
                current_log = get_latest_tunnel_log_file()
                if current_log.is_file():
                    lines = current_log.read_text(encoding="utf-8", errors="replace").splitlines()
                    result = {"success": True, "text": "\n".join(lines[-300:]) or "Tunnel 로그가 비어 있습니다."}
                else:
                    result = {"success": True, "text": "아직 Tunnel 로그 파일이 없습니다."}
            else:
                raise ValueError(f"지원하지 않는 작업입니다: {self.action}")
        except Exception as exc:
            result = {"success": False, "message": f"{type(exc).__name__}: {exc}"}
        self.result_ready.emit({"action": self.action, "result": result})


class ExternalStartWorker(QThread):
    result_ready = Signal(dict)

    def run(self):
        tunnel_started_here = False
        server_restarted = False

        try:
            server_status = get_process_status()

            if server_status.get("running") and not server_status.get("managed"):
                self.result_ready.emit({
                    "success": False,
                    "message": (
                        "MCP 서버가 Connector가 아닌 다른 방식으로 실행 중입니다. "
                        "기존 서버를 종료한 뒤 외부 연결을 다시 시작하세요. "
                        "현재 실행 중인 서버는 안전을 위해 자동 종료하지 않았습니다."
                    ),
                    "server": server_status,
                })
                return

            tunnel_status = get_tunnel_status()
            if not tunnel_status.get("success"):
                self.result_ready.emit({
                    "success": False,
                    "message": tunnel_status.get(
                        "message", "기존 Cloudflare Tunnel 상태를 확인할 수 없습니다."
                    ),
                })
                return

            if tunnel_status.get("running"):
                tunnel_url = tunnel_status.get("url", "")
                tunnel_result = tunnel_status
            else:
                tunnel_result = start_cloudflare_tunnel(check_mcp=False)
                tunnel_started_here = bool(tunnel_result.get("success"))
                tunnel_url = tunnel_result.get("url", "")

            if not tunnel_result.get("success"):
                self.result_ready.emit({
                    "success": False,
                    "message": tunnel_result.get(
                        "message", "Cloudflare Tunnel 시작에 실패했습니다."
                    ),
                    "tunnel": tunnel_result,
                })
                return

            if not tunnel_url:
                self.result_ready.emit({
                    "success": False,
                    "message": (
                        "Cloudflare Tunnel 프로세스는 실행 중이지만 외부 주소를 "
                        "아직 확인하지 못했습니다. Tunnel 로그를 확인한 뒤 "
                        "상태 새로고침을 눌러 다시 시도하세요."
                    ),
                    "tunnel": tunnel_result,
                    "tunnel_started_here": tunnel_started_here,
                })
                return

            values = dotenv_values(str(ENV_PATH)) if ENV_PATH.is_file() else {}
            configured_hosts = {
                item.strip().lower()
                for item in str(values.get("MCP_ALLOWED_HOSTS") or "").split(",")
                if item.strip()
            }
            tunnel_host = save_allowed_tunnel_host(tunnel_url)
            host_changed = tunnel_host not in configured_hosts

            server_needs_start = not server_status.get("running")

            if server_status.get("running") and server_status.get("managed"):
                mcp_result = check_server_status()

                if host_changed or not mcp_result.get("success"):
                    stop_result = stop_server()
                    if not stop_result.get("success"):
                        self.result_ready.emit({
                            "success": False,
                            "message": "새 외부 주소를 적용하기 위해 기존 MCP 서버를 재시작하지 못했습니다.",
                            "detail": stop_result,
                            "url": tunnel_url,
                        })
                        return
                    server_needs_start = True
                    server_restarted = True
                else:
                    # The current managed server already has this host allowlisted.
                    self.result_ready.emit({
                        "success": True,
                        "message": "MCP 서버와 Cloudflare Tunnel이 이미 준비되어 있습니다.",
                        "url": tunnel_url,
                        "tunnel_host": tunnel_host,
                        "tunnel": tunnel_result,
                        "mcp": mcp_result,
                        "already_ready": True,
                    })
                    return

            if server_needs_start:
                start_result = start_server()
                if not start_result.get("success"):
                    self.result_ready.emit({
                        "success": False,
                        "message": "Cloudflare Tunnel은 준비됐지만 MCP 서버 시작에 실패했습니다.",
                        "detail": start_result,
                        "url": tunnel_url,
                        "tunnel_host": tunnel_host,
                    })
                    return

            mcp_result = {"success": False, "message": "MCP 연결 확인 대기 중"}
            for _ in range(16):
                mcp_result = check_server_status()
                if mcp_result.get("success"):
                    break
                time.sleep(0.5)

            if not mcp_result.get("success"):
                self.result_ready.emit({
                    "success": False,
                    "message": (
                        "MCP 서버 프로세스는 시작됐지만 로컬 MCP 인증 또는 연결 확인에 "
                        "실패했습니다. 토큰과 서버 로그를 확인하세요."
                    ),
                    "detail": mcp_result,
                    "url": tunnel_url,
                    "server_restarted": server_restarted,
                })
                return

            self.result_ready.emit({
                "success": True,
                "message": (
                    "MCP 서버와 Cloudflare Tunnel이 준비됐습니다. "
                    "외부 MCP 주소를 클라이언트 연결 설정에 사용하세요."
                ),
                "url": tunnel_url,
                "tunnel_host": tunnel_host,
                "server_restarted": server_restarted,
                "tunnel": tunnel_result,
                "mcp": mcp_result,
            })

        except Exception as exc:
            self.result_ready.emit({
                "success": False,
                "message": f"외부 연결 시작 실패: {type(exc).__name__}: {exc}",
                "tunnel_started_here": tunnel_started_here,
                "server_restarted": server_restarted,
            })


class ExternalStopWorker(QThread):
    result_ready = Signal(dict)

    def run(self):
        tunnel_result = stop_cloudflare_tunnel()
        server_status = get_process_status()

        if not server_status.get("running"):
            server_result = {
                "success": True,
                "message": "MCP 서버는 이미 중지되어 있습니다.",
            }
        elif server_status.get("managed"):
            server_result = stop_server()
        else:
            server_result = {
                "success": False,
                "message": (
                    "MCP 서버가 Connector 관리 대상이 아니므로 종료하지 않았습니다."
                ),
            }

        success = bool(tunnel_result.get("success")) and bool(
            server_result.get("success")
        )

        self.result_ready.emit({
            "success": success,
            "message": (
                "외부 접속과 Connector 관리 MCP 서버를 종료했습니다."
                if success
                else "일부 종료 작업에 실패했거나 관리 대상이 아닌 서버가 남아 있습니다."
            ),
            "tunnel": tunnel_result,
            "server": server_result,
        })


class AgentConnectorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Agent Connector")
        self.resize(1220, 820)
        self.setMinimumSize(1000, 680)

        self.status_labels = {}
        self._workers = []
        self._active_workers = {}
        self.diagnostic_package_path = None
        self.current_token = ""
        self.current_claude_token = ""
        self.current_tunnel_url = ""

        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QHBoxLayout(root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setFixedWidth(225)
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(18, 25, 18, 18)
        sidebar_layout.setSpacing(9)

        logo = QLabel("Agent Connector")
        logo.setObjectName("logo")
        sidebar_layout.addWidget(logo)
        subtitle = QLabel("LOCAL AGENT MANAGER")
        subtitle.setObjectName("subtitle")
        sidebar_layout.addWidget(subtitle)
        sidebar_layout.addSpacing(26)

        self.pages = QStackedWidget()
        self.page_names = [
            "대시보드",
            "에이전트 관리",
            "서버 관리",
            "진단 및 로그",
            "프로그램 정보",
        ]
        self.nav_buttons = []
        page_creators = [
            self.create_dashboard,
            self.create_agents_page,
            self.create_server_page,
            self.create_diagnostics_page,
            self.create_program_page,
        ]

        for index, (name, creator) in enumerate(zip(self.page_names, page_creators)):
            button = QPushButton(name)
            button.setObjectName("navButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, i=index: self.change_page(i))
            sidebar_layout.addWidget(button)
            self.nav_buttons.append(button)
            self.pages.addWidget(creator())

        sidebar_layout.addStretch()
        version = QLabel("Agent Connector")
        version.setObjectName("version")
        sidebar_layout.addWidget(version)
        main_layout.addWidget(sidebar)
        main_layout.addWidget(self.pages, 1)

        self.setStyleSheet("""
            QMainWindow { background: #f3f5f9; }
            #sidebar { background: #202938; }
            #logo { color: white; font-size: 21px; font-weight: 700; }
            #subtitle { color: #9ca9bb; font-size: 10px; letter-spacing: 2px; }
            #navButton { color: #d5dce7; background: transparent; border: none; border-radius: 7px; padding: 13px; text-align: left; font-size: 14px; }
            #navButton:hover { background: #354258; }
            #navButton[selected="true"] { background: #3b82f6; color: white; font-weight: 700; }
            #version { color: #8995a7; font-size: 10px; }
            #content { background: #f3f5f9; }
            #pageTitle { color: #202938; font-size: 25px; font-weight: 700; }
            #description { color: #667085; font-size: 13px; }
            #sectionTitle { color: #344054; font-size: 16px; font-weight: 700; }
            #statusCard, QGroupBox { background: white; border: 1px solid #e1e6ee; border-radius: 10px; }
            #cardTitle { color: #667085; font-size: 13px; }
            #cardValue { color: #202938; font-size: 23px; font-weight: 700; }
            #detailText { color: #667085; font-size: 12px; }
            #toolList, #agentDetails, #logView, #diagnosticOutput, #resultView { background: white; border: 1px solid #e1e6ee; border-radius: 9px; padding: 12px; color: #344054; }
            #primaryButton { background: #2563eb; color: white; border: none; border-radius: 7px; padding: 11px 17px; font-weight: 700; }
            #primaryButton:hover { background: #1d4ed8; border: 1px solid #1746a2; }
            #primaryButton:pressed { background: #1746a2; padding-top: 13px; padding-bottom: 9px; }
            #primaryButton:disabled, #actionButton:disabled { background: #9ca3af; }
            #actionButton { background: #2563eb; color: white; border: none; border-radius: 7px; padding: 10px 15px; font-weight: 700; }
            #actionButton:hover { background: #1d4ed8; }
            #actionButton:pressed { background: #1746a2; padding-top: 12px; padding-bottom: 8px; }
            #navButton:pressed { background: #43536d; }
            #secondaryButton { background: white; color: #344054; border: 1px solid #d0d5dd; border-radius: 7px; padding: 9px 14px; font-weight: 600; }
            #secondaryButton:hover { background: #eff6ff; border-color: #93c5fd; color: #1d4ed8; }
            #secondaryButton:pressed { background: #dbeafe; padding-top: 11px; padding-bottom: 7px; }
            #dangerButton { background: #fff1f0; color: #b42318; border: 1px solid #fecdca; border-radius: 7px; padding: 9px 14px; font-weight: 600; }
            #dangerButton:hover { background: #fee4e2; border-color: #fda29b; }
            #dangerButton:pressed { background: #fecdca; padding-top: 11px; padding-bottom: 7px; }
            QPushButton:disabled { color: #98a2b3; background: #f2f4f7; border-color: #e4e7ec; }
            QListWidget { background: white; border: 1px solid #e1e6ee; border-radius: 8px; padding: 5px; }
            QListWidget::item { color: #202938; padding: 11px; margin: 3px; border: 1px solid #e1e6ee; border-radius: 5px; }
            QListWidget::item:selected { background: #dbeafe; color: #1d4ed8; border-color: #3b82f6; }
            QTextEdit, QLineEdit { background: white; border: 1px solid #d0d5dd; border-radius: 7px; padding: 9px; color: #344054; }
            QLineEdit:read-only { background: #f8fafc; }
            QProgressBar { background: #e5eaf1; border: none; border-radius: 4px; }
            QProgressBar::chunk { background: #3984e8; border-radius: 4px; }
            QGroupBox { color: #202938; margin-top: 12px; padding: 14px; font-weight: 700; }
            QGroupBox::title { color: #202938; subcontrol-origin: margin; left: 12px; padding: 0 5px; }
        """)

        self.change_page(0)
        self.refresh_dashboard()
        self.refresh_agents()
        self.refresh_program_info()

    def page(self, title_text, description_text=""):
        content = QWidget()
        content.setObjectName("content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(34, 28, 34, 26)
        layout.setSpacing(14)

        title = QLabel(title_text)
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        if description_text:
            description = QLabel(description_text)
            description.setObjectName("description")
            description.setWordWrap(True)
            layout.addWidget(description)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setStyleSheet("""
            QScrollBar:vertical {
                width: 15px;
                background: #202630;
                margin: 0px;
                border-radius: 7px;
            }
            QScrollBar::handle:vertical {
                background: #65758a;
                min-height: 35px;
                border-radius: 7px;
            }
            QScrollBar::handle:vertical:hover {
                background: #8b9bb0;
            }
            QScrollBar::handle:vertical:pressed {
                background: #a8b8cc;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)

        return scroll, layout

    def create_card(self, title, key, detail=""):
        card = QFrame()
        card.setObjectName("statusCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        value_label = QLabel("조회 중...")
        value_label.setObjectName("cardValue")
        detail_label = QLabel(detail)
        detail_label.setObjectName("detailText")
        detail_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addWidget(detail_label)
        self.status_labels[key] = {"value": value_label, "detail": detail_label}
        return card

    def create_dashboard(self):
        page, layout = self.page("대시보드", "Connector의 준비 상태를 확인하고 외부 연결을 시작합니다.")

        action_row = QHBoxLayout()
        action_row.addStretch()
        self.dashboard_refresh_button = QPushButton("상태 새로고침")
        self.dashboard_refresh_button.setObjectName("secondaryButton")
        self.dashboard_refresh_button.clicked.connect(self.refresh_dashboard)
        action_row.addWidget(self.dashboard_refresh_button)
        layout.addLayout(action_row)

        refresh_info = QHBoxLayout()
        self.dashboard_refresh_status = QLabel("아직 상태를 조회하지 않았습니다.")
        self.dashboard_refresh_status.setObjectName("description")
        refresh_info.addWidget(self.dashboard_refresh_status, 1)
        self.dashboard_last_checked = QLabel("마지막 확인: -")
        self.dashboard_last_checked.setObjectName("description")
        refresh_info.addWidget(self.dashboard_last_checked)
        layout.addLayout(refresh_info)

        self.dashboard_progress = QProgressBar()
        self.dashboard_progress.setRange(0, 100)
        self.dashboard_progress.setValue(0)
        self.dashboard_progress.setTextVisible(False)
        self.dashboard_progress.setFixedHeight(8)
        self.dashboard_progress.setStyleSheet(
            "QProgressBar { background: #e5eaf1; border: none; border-radius: 4px; }"
            "QProgressBar::chunk { background: #3984e8; border-radius: 4px; }"
        )
        layout.addWidget(self.dashboard_progress)

        cards = QHBoxLayout()
        cards.addWidget(self.create_card("MCP 서버", "server", "로컬 에이전트 실행 환경"))
        cards.addWidget(self.create_card("외부 접속", "tunnel", "Cloudflare Tunnel"))
        cards.addWidget(self.create_card("설치된 에이전트", "agents", "로컬에 등록된 패키지"))
        cards.addWidget(self.create_card("MCP 도구", "tools", "외부 AI에 제공되는 도구"))
        layout.addLayout(cards)

        start_group = QGroupBox("빠른 실행")
        start_layout = QVBoxLayout(start_group)
        self.external_start_button = QPushButton("외부 연결 시작")
        self.external_start_button.setObjectName("primaryButton")
        self.external_start_button.setMinimumHeight(48)
        self.external_start_button.clicked.connect(self.start_external_connection)
        self.external_stop_button = QPushButton("외부 연결 종료")
        self.external_stop_button.setObjectName("dangerButton")
        self.external_stop_button.clicked.connect(self.stop_external_connection)
        start_layout.addWidget(self.external_start_button)
        start_layout.addWidget(QLabel("MCP 서버와 외부 접속을 순서대로 준비합니다."))
        start_layout.addWidget(self.external_stop_button)
        layout.addWidget(start_group)

        tools_title = QLabel("등록된 MCP 도구")
        tools_title.setObjectName("sectionTitle")
        layout.addWidget(tools_title)
        self.tool_list = QLabel("도구 목록을 조회하고 있습니다.")
        self.tool_list.setObjectName("toolList")
        self.tool_list.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.tool_list.setWordWrap(True)
        self.tool_list.setMinimumHeight(155)
        layout.addWidget(self.tool_list, 1)
        self.dashboard_message = QLabel("상태를 확인하고 있습니다.")
        self.dashboard_message.setObjectName("description")
        self.dashboard_message.setWordWrap(True)
        layout.addWidget(self.dashboard_message)
        return page

    def create_agents_page(self):
        page, layout = self.page("에이전트 관리", "에이전트 패키지를 가져와 로컬 Connector에 등록하거나 삭제합니다.")
        buttons = QHBoxLayout()
        self.agent_refresh_button = QPushButton("목록 새로고침")
        self.install_button = QPushButton("에이전트 가져오기")
        self.remove_button = QPushButton("에이전트 삭제")
        for button in (self.agent_refresh_button, self.install_button, self.remove_button):
            button.setObjectName("actionButton")
            buttons.addWidget(button)
        buttons.addStretch()
        self.agent_refresh_button.clicked.connect(self.refresh_agents)
        self.install_button.clicked.connect(self.select_agent_package)
        self.remove_button.clicked.connect(self.remove_selected_agent)
        layout.addLayout(buttons)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.agent_list = QListWidget()
        self.agent_list.currentItemChanged.connect(self.show_agent_details)
        self.agent_details = QTextEdit()
        self.agent_details.setObjectName("agentDetails")
        self.agent_details.setReadOnly(True)
        self.agent_details.setPlaceholderText("에이전트를 선택하면 상세 정보가 표시됩니다.")
        splitter.addWidget(self.agent_list)
        splitter.addWidget(self.agent_details)
        splitter.setSizes([360, 560])
        layout.addWidget(splitter, 1)

        self.agent_message = QLabel("에이전트 목록을 불러오는 중...")
        self.agent_message.setObjectName("description")
        self.agent_message.setWordWrap(True)
        layout.addWidget(self.agent_message)
        return page

    def create_server_page(self):
        page, layout = self.page(
            "서버 관리",
            "MCP 서버와 Cloudflare Tunnel의 상태를 한곳에서 확인하고 각각 제어합니다.",
        )

        self.server_refresh_status = QLabel("서버 상태를 아직 확인하지 않았습니다.")
        self.server_refresh_status.setObjectName("description")
        layout.addWidget(self.server_refresh_status)
        self.server_refresh_progress = QProgressBar()
        self.server_refresh_progress.setRange(0, 100)
        self.server_refresh_progress.setValue(0)
        self.server_refresh_progress.setTextVisible(False)
        self.server_refresh_progress.setFixedHeight(7)
        layout.addWidget(self.server_refresh_progress)

        server_group = QGroupBox("MCP 서버")
        server_layout = QVBoxLayout(server_group)
        self.server_status_label = QLabel("상태 확인 전")
        self.server_status_label.setObjectName("sectionTitle")
        server_layout.addWidget(self.server_status_label)
        row = QHBoxLayout()
        self.server_start_button = QPushButton("MCP 서버 시작")
        self.server_stop_button = QPushButton("MCP 서버 중지")
        self.server_check_button = QPushButton("상태 새로고침")
        self.server_start_button.setObjectName("actionButton")
        self.server_stop_button.setObjectName("dangerButton")
        self.server_check_button.setObjectName("secondaryButton")
        row.addWidget(self.server_start_button)
        row.addWidget(self.server_stop_button)
        row.addWidget(self.server_check_button)
        server_layout.addLayout(row)
        self.server_start_button.clicked.connect(lambda: self.run_operation("start_server"))
        self.server_stop_button.clicked.connect(lambda: self.run_operation("stop_server"))
        self.server_check_button.clicked.connect(self.refresh_dashboard)
        layout.addWidget(server_group)

        tunnel_group = QGroupBox("Cloudflare Tunnel")
        tunnel_layout = QVBoxLayout(tunnel_group)
        self.tunnel_status_label = QLabel("상태 확인 전")
        self.tunnel_status_label.setObjectName("sectionTitle")
        tunnel_layout.addWidget(self.tunnel_status_label)

        tunnel_controls = QHBoxLayout()
        self.tunnel_start_button = QPushButton("Tunnel 시작")
        self.tunnel_stop_button = QPushButton("Tunnel 중지")
        self.tunnel_refresh_button = QPushButton("상태 새로고침")
        self.tunnel_start_button.setObjectName("actionButton")
        self.tunnel_stop_button.setObjectName("dangerButton")
        self.tunnel_refresh_button.setObjectName("secondaryButton")
        tunnel_controls.addWidget(self.tunnel_start_button)
        tunnel_controls.addWidget(self.tunnel_stop_button)
        tunnel_controls.addWidget(self.tunnel_refresh_button)
        tunnel_layout.addLayout(tunnel_controls)

        public_row = QHBoxLayout()
        self.server_public_url_edit = QLineEdit()
        self.server_public_url_edit.setReadOnly(True)
        self.server_public_url_edit.setPlaceholderText(
            "Tunnel 실행 후 외부 MCP 주소가 표시됩니다."
        )
        self.public_url_edit = self.server_public_url_edit
        self.server_public_url_copy_button = QPushButton("외부 주소 복사")
        self.server_public_url_copy_button.setObjectName("secondaryButton")
        self.server_public_url_copy_button.clicked.connect(self.copy_public_url)
        public_row.addWidget(self.server_public_url_edit, 1)
        public_row.addWidget(self.server_public_url_copy_button)
        tunnel_layout.addLayout(public_row)

        self.tunnel_result = QTextEdit()
        self.tunnel_result.setObjectName("resultView")
        self.tunnel_result.setReadOnly(True)
        self.tunnel_result.setMaximumHeight(105)
        self.tunnel_result.setPlaceholderText(
            "Tunnel 실행·중지 결과와 오류가 여기에 표시됩니다."
        )
        tunnel_layout.addWidget(self.tunnel_result)

        self.tunnel_start_button.clicked.connect(
            lambda: self.run_operation("tunnel_start")
        )
        self.tunnel_stop_button.clicked.connect(
            lambda: self.run_operation("tunnel_stop")
        )
        self.tunnel_refresh_button.clicked.connect(self.refresh_dashboard)
        layout.addWidget(tunnel_group)

        connection_group = QGroupBox("외부 AI 연결 정보")
        connection_layout = QFormLayout(connection_group)

        self.local_url_edit = QLineEdit(MCP_URL)
        self.local_url_edit.setReadOnly(True)
        local_row = QHBoxLayout()
        local_row.addWidget(self.local_url_edit, 1)
        self.local_url_copy_button = QPushButton("로컬 주소 복사")
        self.local_url_copy_button.setObjectName("secondaryButton")
        self.local_url_copy_button.clicked.connect(
            lambda: self.copy_text(MCP_URL, "로컬 MCP 주소")
        )
        local_row.addWidget(self.local_url_copy_button)
        connection_layout.addRow("로컬 MCP 주소", local_row)

        token_row = QHBoxLayout()
        self.token_edit = QLineEdit()
        self.token_edit.setReadOnly(True)
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.setPlaceholderText(
            "MCP_AUTH_TOKEN이 설정되지 않았습니다."
        )
        token_row.addWidget(self.token_edit, 1)

        self.token_show_button = QPushButton("전체 보기")
        self.token_copy_button = QPushButton("토큰 복사")
        self.token_generate_button = QPushButton("새 토큰 생성")
        for button in (
            self.token_show_button,
            self.token_copy_button,
            self.token_generate_button,
        ):
            button.setObjectName("secondaryButton")
            token_row.addWidget(button)

        self.token_show_button.clicked.connect(self.toggle_token_visibility)
        self.token_copy_button.clicked.connect(self.copy_token)
        self.token_generate_button.clicked.connect(self.generate_token)
        connection_layout.addRow("인증 토큰", token_row)

        self.token_status_label = QLabel("토큰 상태 확인 전")
        self.token_status_label.setObjectName("description")
        connection_layout.addRow("인증 상태", self.token_status_label)

        claude_token_row = QHBoxLayout()
        self.claude_token_edit = QLineEdit()
        self.claude_token_edit.setReadOnly(True)
        self.claude_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.claude_token_edit.setPlaceholderText(
            "CLAUDE_TEST_TOKEN이 설정되지 않았습니다."
        )
        claude_token_row.addWidget(self.claude_token_edit, 1)

        self.claude_token_show_button = QPushButton("전체 보기")
        self.claude_token_copy_button = QPushButton("토큰 복사")
        self.claude_token_generate_button = QPushButton("토큰 재발급")

        for button in (
            self.claude_token_show_button,
            self.claude_token_copy_button,
            self.claude_token_generate_button,
        ):
            button.setObjectName("secondaryButton")
            claude_token_row.addWidget(button)

        self.claude_token_show_button.clicked.connect(
            self.toggle_claude_token_visibility
        )
        self.claude_token_copy_button.clicked.connect(
            self.copy_claude_token
        )
        self.claude_token_generate_button.clicked.connect(
            self.generate_claude_token
        )

        connection_layout.addRow("Claude 연결 토큰", claude_token_row)

        self.claude_token_status_label = QLabel("Claude 토큰 상태 확인 전")
        self.claude_token_status_label.setObjectName("description")
        connection_layout.addRow("Claude 토큰 상태", self.claude_token_status_label)

        layout.addWidget(connection_group)

        note = QLabel(
            "MCP 서버와 Cloudflare Tunnel은 각각 독립적으로 실행·중지할 수 있습니다. "
            "외부 AI 서비스에서 사용하려면 두 프로세스가 모두 실행 중이어야 합니다. "
            "Tunnel 주소가 바뀌면 외부 접속 주소도 새 주소로 갱신됩니다."
        )
        note.setObjectName("description")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        self.refresh_token_display()
        return page

    def create_diagnostics_page(self):
        page, layout = self.page("진단 및 로그", "연결 상태와 패키지 보안을 점검하고 문제가 발생했을 때 상세 로그를 확인합니다.")

        row = QHBoxLayout()
        self.diagnostic_select_button = QPushButton("검사할 패키지 선택")
        self.security_button = QPushButton("보안 검사")
        self.integrity_button = QPushButton("무결성 검사")
        self.log_refresh_button = QPushButton("최신 MCP 로그 보기")
        self.tunnel_log_refresh_button = QPushButton("최신 Tunnel 로그 보기")
        for button in (self.diagnostic_select_button, self.security_button, self.integrity_button, self.log_refresh_button, self.tunnel_log_refresh_button):
            button.setObjectName("secondaryButton")
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)

        self.diagnostic_path_label = QLabel("선택된 패키지: 없음")
        self.diagnostic_path_label.setObjectName("description")
        self.diagnostic_path_label.setWordWrap(True)
        layout.addWidget(self.diagnostic_path_label)

        self.diagnostic_output = QTextEdit()
        self.diagnostic_output.setObjectName("diagnosticOutput")
        self.diagnostic_output.setReadOnly(True)
        self.diagnostic_output.setMinimumHeight(160)
        self.diagnostic_output.setPlaceholderText("보안 검사 및 무결성 검사 결과가 표시됩니다.")
        layout.addWidget(self.diagnostic_output)

        log_header = QHBoxLayout()
        self.log_title = QLabel("MCP 서버 로그 · 최신 실행 기록")
        self.log_title.setObjectName("sectionTitle")
        log_header.addWidget(self.log_title)
        log_header.addStretch()
        self.open_logs_button = QPushButton("로그 폴더 열기")
        self.open_logs_button.setObjectName("secondaryButton")
        self.open_logs_button.clicked.connect(lambda: self.open_folder(LOG_DIR))
        log_header.addWidget(self.open_logs_button)
        layout.addLayout(log_header)
        log_policy = QLabel(
            "각 실행 회차의 로그는 별도 파일로 보관되며, 새 실행이 이전 기록을 덮어쓰지 않습니다."
        )
        log_policy.setObjectName("description")
        layout.addWidget(log_policy)

        self.log_view = QTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, 1)

        self.diagnostic_select_button.clicked.connect(self.select_diagnostic_package)
        self.security_button.clicked.connect(lambda: self.run_diagnostic("security"))
        self.integrity_button.clicked.connect(lambda: self.run_diagnostic("integrity"))
        self.log_refresh_button.clicked.connect(lambda: self.run_operation("logs"))
        self.tunnel_log_refresh_button.clicked.connect(lambda: self.run_operation("tunnel_logs"))
        return page

    def create_program_page(self):
        page, layout = self.page("프로그램 정보", "일반 사용자가 자주 변경할 필요는 없지만 문제 해결에 필요한 설치 및 실행 환경 정보입니다.")
        group = QGroupBox("실행 환경 정보")
        form = QFormLayout(group)
        self.program_values = {}
        for key, label in (
            ("project", "프로젝트 경로"),
            ("python", "가상환경 Python"),
            ("server", "MCP 서버 파일"),
            ("env", "환경 변수 파일"),
            ("mcp_log", "최신 MCP 실행 로그"),
            ("tunnel_log", "최신 Cloudflare 실행 로그"),
        ):
            value = QLabel("-")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setWordWrap(True)
            self.program_values[key] = value
            form.addRow(label, value)
        layout.addWidget(group)

        row = QHBoxLayout()
        self.program_refresh_button = QPushButton("정보 새로고침")
        self.open_project_button = QPushButton("프로젝트 폴더 열기")
        self.open_program_logs_button = QPushButton("로그 폴더 열기")
        for button in (self.program_refresh_button, self.open_project_button, self.open_program_logs_button):
            button.setObjectName("secondaryButton")
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        self.program_refresh_button.clicked.connect(self.refresh_program_info)
        self.open_project_button.clicked.connect(lambda: self.open_folder(BASE_DIR))
        self.open_program_logs_button.clicked.connect(lambda: self.open_folder(LOG_DIR))
        layout.addStretch()
        return page

    def set_card(self, key, value, detail):
        self.status_labels[key]["value"].setText(str(value))
        self.status_labels[key]["detail"].setText(str(detail))

    def start_worker(self, key, worker, on_finished=None):
        existing = self._active_workers.get(key)
        if existing is not None and existing.isRunning():
            return False

        self._workers.append(worker)
        self._active_workers[key] = worker

        def cleanup(w=worker, k=key, callback=on_finished):
            if w in self._workers:
                self._workers.remove(w)
            if self._active_workers.get(k) is w:
                self._active_workers.pop(k, None)
            if callback:
                callback()

        worker.finished.connect(cleanup)
        worker.finished.connect(worker.deleteLater)
        worker.start()
        return True

    def refresh_dashboard(self):
        existing = self._active_workers.get("status")
        if existing is not None and existing.isRunning():
            self.dashboard_refresh_status.setText(
                "상태 조회가 이미 진행 중입니다. 잠시 기다려 주세요."
            )
            self.server_refresh_status.setText(
                "상태 조회가 이미 진행 중입니다."
            )
            return

        self.dashboard_refresh_button.setEnabled(False)
        self.server_check_button.setEnabled(False)
        self.tunnel_refresh_button.setEnabled(False)
        self.dashboard_refresh_button.setText("조회 중...")
        self.dashboard_refresh_status.setText("상태 조회를 시작합니다.")
        self.dashboard_progress.setValue(0)
        self.server_refresh_status.setText("서버 상태를 조회하고 있습니다.")
        self.server_refresh_progress.setValue(0)

        worker = StatusWorker()
        worker.progress.connect(self.update_dashboard_progress)
        worker.result_ready.connect(self.update_dashboard)

        def finish_refresh():
            self.dashboard_refresh_button.setEnabled(True)
            self.server_check_button.setEnabled(True)
            self.tunnel_refresh_button.setEnabled(True)
            self.dashboard_refresh_button.setText("상태 새로고침")
            if self.dashboard_progress.value() < 100:
                self.dashboard_refresh_status.setText(
                    "상태 조회가 정상적으로 완료되지 않았습니다. 다시 시도하거나 진단 로그를 확인하세요."
                )

        started = self.start_worker("status", worker, finish_refresh)
        if not started:
            finish_refresh()
            self.dashboard_refresh_status.setText(
                "다른 상태 조회 작업이 진행 중입니다."
            )

    def update_dashboard_progress(self, message, value):
        self.dashboard_refresh_status.setText(message)
        self.dashboard_progress.setValue(value)
        self.server_refresh_status.setText(message)
        self.server_refresh_progress.setValue(value)

    def update_dashboard(self, results):
        server = results.get("server", {})
        mcp = results.get("mcp", {})
        tunnel = results.get("tunnel", {})
        agents = results.get("agents", [])

        server_running = bool(server.get("running"))
        self.set_card(
            "server",
            "실행 중" if server_running else "중지됨",
            server.get("message", "상태 확인 실패"),
        )
        self.server_status_label.setText(
            "MCP 서버 온라인"
            if server_running and mcp.get("success")
            else (
                "프로세스 실행 중 · MCP 연결 실패"
                if server_running
                else "MCP 서버 오프라인"
            )
        )

        tunnel_running = bool(tunnel.get("running"))
        tunnel_check_ok = bool(tunnel.get("success"))
        self.set_card(
            "tunnel",
            "실행 중" if tunnel_running else ("중지됨" if tunnel_check_ok else "확인 실패"),
            tunnel.get("message", "Tunnel 상태 확인 실패"),
        )
        self.tunnel_status_label.setText(
            "Cloudflare Tunnel 온라인"
            if tunnel_running
            else ("Cloudflare Tunnel 오프라인" if tunnel_check_ok else "Cloudflare Tunnel 상태 확인 실패")
        )

        if isinstance(agents, list):
            valid = [agent for agent in agents if isinstance(agent, dict) and agent.get("name") != "INVALID"]
            invalid_count = len(agents) - len(valid)
            self.set_card("agents", f"{len(valid)}개", f"정상 {len(valid)}개 / 오류 {invalid_count}개")
        else:
            self.set_card("agents", "조회 실패", agents.get("error", "에이전트 목록 조회 실패"))

        tools = mcp.get("tools", []) if isinstance(mcp, dict) else []
        if mcp.get("success"):
            self.set_card("tools", f"{len(tools)}개", "MCP 서버에서 조회한 도구")
            self.tool_list.setText("\n".join(f"• {tool}" for tool in tools) if tools else "등록된 MCP 도구가 없습니다.")
        else:
            mcp_error = mcp.get("message", "MCP 연결 실패")
            self.set_card("tools", "확인 불가", mcp_error)
            self.tool_list.setText(
                "MCP 연결이 확인되지 않아 도구 목록을 조회할 수 없습니다.\n"
                f"원인: {mcp_error}"
            )

        public_url = tunnel.get("url", "") if isinstance(tunnel, dict) else ""
        self.current_tunnel_url = public_url
        self.public_url_edit.setText(public_url)
        self.server_public_url_edit.setText(public_url)

        if mcp.get("success") and tunnel_running:
            self.dashboard_message.setText("로컬 MCP 연결과 Tunnel 프로세스가 실행 중입니다. 외부 호스트 허용 여부는 별도 연결 테스트가 필요합니다.")
        elif server_running and not tunnel_running:
            self.dashboard_message.setText("로컬 MCP 서버는 실행 중입니다. 외부 AI 서비스에서 사용하려면 Tunnel도 시작해야 합니다.")
        else:
            self.dashboard_message.setText("외부 연결을 시작하려면 '외부 연결 시작'을 누르세요.")

        checked_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.dashboard_progress.setValue(100)
        self.dashboard_refresh_status.setText("상태 조회 완료")
        self.dashboard_last_checked.setText(f"마지막 확인: {checked_at}")
        self.server_refresh_status.setText(f"서버 상태 조회 완료 · {checked_at}")
        self.server_refresh_progress.setValue(100)
        self.server_status_label.setText(
            "MCP 서버 온라인"
            if server_running and mcp.get("success")
            else (
                "프로세스 실행 중 · MCP 연결 실패"
                if server_running
                else "MCP 서버 오프라인"
            )
        )
        self.tunnel_status_label.setText(
            "Cloudflare Tunnel 온라인"
            if tunnel_running
            else (
                "Cloudflare Tunnel 오프라인"
                if tunnel_check_ok
                else "Cloudflare Tunnel 상태 확인 실패"
            )
        )
        self.refresh_token_display()

    def refresh_agents(self):
        self.run_agent_operation("list")

    def select_agent_package(self):
        existing = self._active_workers.get("agents")
        if existing is not None and existing.isRunning():
            return
        folder = QFileDialog.getExistingDirectory(self, "가져올 에이전트 패키지 폴더 선택")
        if not folder:
            return
        manifest_path = Path(folder) / "manifest.json"
        try:
            with manifest_path.open("r", encoding="utf-8-sig") as file:
                manifest = json.load(file)
            if not isinstance(manifest, dict):
                raise ValueError("manifest.json 최상위 값은 객체여야 합니다.")
            agent_id = manifest.get("id")
            name = manifest.get("name", "이름 없음")
            description = manifest.get("description", "설명 없음")
            if not isinstance(agent_id, str) or not agent_id.strip():
                raise ValueError("유효한 에이전트 ID가 없습니다.")
            if not isinstance(name, str) or not isinstance(description, str):
                raise ValueError("에이전트 이름 또는 설명 형식이 올바르지 않습니다.")
        except Exception as exc:
            QMessageBox.warning(self, "패키지 확인 실패", f"manifest.json을 읽을 수 없습니다.\n\n{exc}")
            return

        preview = (
            f"이름: {name}\nID: {agent_id}\n설명: {description}\n\n경로: {folder}\n\n"
            "가져오면 보안 및 무결성 검사를 거쳐 로컬 Connector에 등록합니다. 계속할까요?"
        )
        answer = QMessageBox.question(
            self,
            "에이전트 가져오기 확인",
            preview,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.run_agent_operation("install", folder)

    def remove_selected_agent(self):
        existing = self._active_workers.get("agents")
        if existing is not None and existing.isRunning():
            return
        item = self.agent_list.currentItem()
        if item is None:
            QMessageBox.warning(self, "에이전트 삭제", "삭제할 에이전트를 선택해 주세요.")
            return
        agent = item.data(Qt.ItemDataRole.UserRole)
        agent_id = agent.get("id") if isinstance(agent, dict) else None
        if not agent_id or agent.get("name") == "INVALID":
            QMessageBox.warning(self, "삭제할 수 없음", "선택한 에이전트 정보가 올바르지 않습니다.")
            return
        answer = QMessageBox.question(
            self,
            "에이전트 삭제 확인",
            f"'{agent.get('name')}' 에이전트를 삭제할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.run_agent_operation("remove", agent_id)

    def run_agent_operation(self, action, value=None):
        self.set_agent_controls(False)
        messages = {
            "list": "에이전트 목록 조회 중...",
            "install": "에이전트 등록 및 검증 중...",
            "remove": "에이전트 삭제 중...",
        }
        self.agent_message.setText(messages[action])
        worker = AgentWorker(action, value)
        worker.result_ready.connect(self.handle_agent_result)
        started = self.start_worker("agents", worker, lambda: self.set_agent_controls(True))
        if not started:
            self.set_agent_controls(True)

    def handle_agent_result(self, data):
        self.agent_list.clear()
        agents = data.get("agents", [])
        if isinstance(agents, list):
            for agent in agents:
                if not isinstance(agent, dict):
                    continue
                name = agent.get("name", "이름 없음")
                agent_id = agent.get("id", "ID 없음")
                label = f"[오류 항목] {agent_id}" if name == "INVALID" else f"{name} ({agent_id})"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, agent)
                self.agent_list.addItem(item)

        operation = data.get("operation", {})
        message = operation.get("message", "작업 결과를 확인할 수 없습니다.")
        self.agent_message.setText(message if operation.get("success") else "작업 실패: " + message)
        self.agent_details.clear()
        self.refresh_dashboard()

    def show_agent_details(self, current, previous=None):
        if current is None:
            self.agent_details.clear()
            return
        agent = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(agent, dict):
            self.agent_details.clear()
            return
        details = [
            f"이름: {agent.get('name', '-')}",
            f"ID: {agent.get('id', '-')}",
            f"설명: {agent.get('description', '-')}",
            f"설치 경로: {agent.get('path', '-')}",
        ]
        self.agent_details.setPlainText("\n\n".join(details))

    def set_agent_controls(self, enabled):
        for button in (self.agent_refresh_button, self.install_button, self.remove_button):
            button.setEnabled(enabled)

    def run_operation(self, action, value=None):
        worker = OperationWorker(action, value)
        worker.result_ready.connect(self.handle_operation_result)
        worker.finished.connect(lambda: self.set_operation_controls(True))
        for button in (
            self.server_start_button,
            self.server_stop_button,
            self.server_check_button,
            self.tunnel_start_button,
            self.tunnel_stop_button,
            self.tunnel_refresh_button,
            self.security_button,
            self.integrity_button,
            self.log_refresh_button,
            self.tunnel_log_refresh_button,
        ):
            button.setEnabled(False)
        started = self.start_worker("operation", worker)
        if not started:
            self.set_operation_controls(True)

    def set_operation_controls(self, enabled):
        for button in (
            self.server_start_button,
            self.server_stop_button,
            self.server_check_button,
            self.tunnel_start_button,
            self.tunnel_stop_button,
            self.tunnel_refresh_button,
            self.security_button,
            self.integrity_button,
            self.log_refresh_button,
            self.tunnel_log_refresh_button,
        ):
            button.setEnabled(enabled)

    def handle_operation_result(self, payload):
        action = payload.get("action")
        result = payload.get("result", {})

        if action in ("logs", "tunnel_logs"):
            text = result.get("text", result.get("message", "로그 조회 실패"))
            self.log_view.setPlainText(text)
            self.log_view.moveCursor(QTextCursor.MoveOperation.End)
            self.log_title.setText(
                "MCP 서버 로그 · 최신 실행 기록"
                if action == "logs"
                else "Cloudflare Tunnel 로그 · 최신 실행 기록"
            )
            return

        if action in ("security", "integrity"):
            title = "보안 검사" if action == "security" else "무결성 검사"
            self.diagnostic_output.setPlainText(title + "\n" + json.dumps(result, ensure_ascii=False, indent=2))
            return

        if action.startswith("tunnel_"):
            self.tunnel_result.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
            self.tunnel_status_label.setText(
                "Cloudflare Tunnel 온라인" if result.get("running") or result.get("success") and action == "tunnel_start"
                else "Cloudflare Tunnel 오프라인 또는 오류"
            )
            if result.get("url"):
                self.current_tunnel_url = result["url"]
                self.public_url_edit.setText(self.current_tunnel_url)
                self.server_public_url_edit.setText(self.current_tunnel_url)
            self.refresh_dashboard()
            return

        self.mcp_result_text = json.dumps(result, ensure_ascii=False, indent=2)
        if action in ("start_server", "stop_server", "process_status", "mcp_status", "refresh_tools"):
            self.server_status_label.setText(result.get("message", "작업 결과를 확인할 수 없습니다."))
            self.refresh_dashboard()

    def select_diagnostic_package(self):
        folder = QFileDialog.getExistingDirectory(self, "검사할 에이전트 패키지 폴더 선택")
        if folder:
            self.diagnostic_package_path = Path(folder)
            self.diagnostic_path_label.setText(f"선택된 패키지: {folder}")

    def run_diagnostic(self, action):
        if not self.diagnostic_package_path or not self.diagnostic_package_path.is_dir():
            QMessageBox.warning(self, "패키지 선택", "먼저 검사할 에이전트 패키지 폴더를 선택해 주세요.")
            return
        self.run_operation(action, str(self.diagnostic_package_path))

    def refresh_token_display(self):
        self.current_token = read_auth_token()
        self.token_edit.setText(self.current_token)

        self.current_claude_token = read_claude_token()
        self.claude_token_edit.setText(self.current_claude_token)

        if self.current_claude_token:
            self.claude_token_status_label.setText(
                "Claude 연결 토큰이 설정되어 있습니다."
            )
            self.claude_token_copy_button.setEnabled(True)
        else:
            self.claude_token_status_label.setText(
                "Claude 연결 토큰이 없습니다."
            )
            self.claude_token_copy_button.setEnabled(False)
        if self.current_token:
            self.token_status_label.setText("인증 토큰이 설정되어 있습니다.")
            self.token_copy_button.setEnabled(True)
        else:
            self.token_status_label.setText("인증 토큰이 없습니다. 새 토큰을 생성해야 MCP 서버를 시작할 수 있습니다.")
            self.token_copy_button.setEnabled(False)

    def toggle_claude_token_visibility(self):
        visible = (
            self.claude_token_edit.echoMode()
            == QLineEdit.EchoMode.Password
        )
        self.claude_token_edit.setEchoMode(
            QLineEdit.EchoMode.Normal
            if visible else QLineEdit.EchoMode.Password
        )
        self.claude_token_show_button.setText(
            "숨기기" if visible else "전체 보기"
        )

    def copy_claude_token(self):
        token = self.current_claude_token or read_claude_token()
        if not token:
            QMessageBox.warning(
                self, "토큰 없음",
                "CLAUDE_TEST_TOKEN이 설정되어 있지 않습니다."
            )
            return

        QApplication.clipboard().setText(token)
        self.claude_token_status_label.setText(
            "Claude 연결 토큰을 클립보드에 복사했습니다."
        )

    def generate_claude_token(self):
        answer = QMessageBox.question(
            self,
            "Claude 연결 토큰 재발급",
            "새 토큰을 발급하면 기존 Claude 연결 주소의 토큰은 더 이상 사용할 수 없습니다. 계속할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            token = secrets.token_urlsafe(32)
            save_claude_token(token)

            self.refresh_token_display()
            self.claude_token_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.claude_token_show_button.setText("숨기기")

            QMessageBox.information(
                self,
                "Claude 토큰 재발급 완료",
                "새 Claude 연결 토큰을 저장했습니다.\n\n"
                "새 토큰을 적용하려면 MCP 서버를 재시작해야 합니다.\n"
                "새 토큰이 포함된 외부 연결 주소를 사용하세요.",
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Claude 토큰 발급 실패",
                str(exc),
            )

    def toggle_token_visibility(self):
        visible = self.token_edit.echoMode() == QLineEdit.EchoMode.Password
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
        self.token_show_button.setText("숨기기" if visible else "전체 보기")

    def copy_token(self):
        token = self.current_token or read_auth_token()
        if not token:
            QMessageBox.warning(self, "토큰 없음", "먼저 인증 토큰을 생성하세요.")
            return
        QApplication.clipboard().setText(token)
        self.dashboard_message.setText("인증 토큰을 클립보드에 복사했습니다.")
        self.token_status_label.setText("인증 토큰을 클립보드에 복사했습니다.")

    def generate_token(self):
        answer = QMessageBox.question(
            self,
            "인증 토큰 새로 생성",
            "새 토큰을 생성하면 기존 토큰은 더 이상 사용할 수 없습니다. 계속할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            token = secrets.token_urlsafe(32)
            save_auth_token(token)
            self.refresh_token_display()
            self.token_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.token_show_button.setText("숨기기")
            QMessageBox.information(
                self,
                "토큰 생성 완료",
                "새 인증 토큰을 저장했습니다.\n\nMCP 서버가 실행 중이었다면 중지한 뒤 다시 시작해야 새 토큰이 적용됩니다.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "토큰 저장 실패", str(exc))

    def copy_text(self, value, label):
        QApplication.clipboard().setText(value)
        self.dashboard_message.setText(f"{label}을(를) 클립보드에 복사했습니다.")

    def copy_public_url(self):
        value = self.current_tunnel_url or self.public_url_edit.text().strip() or self.server_public_url_edit.text().strip()
        if not value:
            QMessageBox.warning(self, "주소 없음", "먼저 Cloudflare Tunnel을 실행해 외부 주소를 생성하세요.")
            return
        self.copy_text(value, "외부 MCP 주소")

    def start_external_connection(self):
        self.external_start_button.setEnabled(False)
        self.external_stop_button.setEnabled(False)
        self.dashboard_message.setText("MCP 서버를 확인하고 외부 접속 통로를 준비하고 있습니다.")
        worker = ExternalStartWorker()
        worker.result_ready.connect(self.handle_external_start_result)
        self.set_operation_controls(False)
        started = self.start_worker(
            "external_start",
            worker,
            lambda: (self.external_start_button.setEnabled(True), self.external_stop_button.setEnabled(True), self.set_operation_controls(True)),
        )
        if not started:
            self.external_start_button.setEnabled(True)
            self.external_stop_button.setEnabled(True)
            self.set_operation_controls(True)

    def handle_external_start_result(self, result):
        self.dashboard_message.setText(result.get("message", "외부 연결 작업이 끝났습니다."))
        if result.get("url"):
            self.current_tunnel_url = result["url"]
            self.public_url_edit.setText(self.current_tunnel_url)
            self.server_public_url_edit.setText(self.current_tunnel_url)
            self.tunnel_result.setPlainText("외부 MCP 주소\n" + self.current_tunnel_url + "\n\n" + result.get("message", ""))
        elif not result.get("success"):
            self.tunnel_result.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
        self.refresh_dashboard()
        self.refresh_token_display()

    def stop_external_connection(self):
        answer = QMessageBox.question(
            self,
            "외부 연결 종료",
            "Cloudflare Tunnel과 Connector가 관리하는 MCP 서버를 모두 종료할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.external_stop_button.setEnabled(False)
        self.external_start_button.setEnabled(False)
        worker = ExternalStopWorker()
        worker.result_ready.connect(self.handle_external_stop_result)
        self.set_operation_controls(False)
        started = self.start_worker(
            "external_stop",
            worker,
            lambda: (self.external_stop_button.setEnabled(True), self.external_start_button.setEnabled(True), self.set_operation_controls(True)),
        )
        if not started:
            self.external_stop_button.setEnabled(True)
            self.set_operation_controls(True)

    def handle_external_stop_result(self, result):
        self.dashboard_message.setText(result.get("message", "외부 연결 종료 작업이 끝났습니다."))
        self.tunnel_result.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
        self.current_tunnel_url = ""
        self.public_url_edit.clear()
        self.server_public_url_edit.clear()
        self.refresh_dashboard()

    def refresh_program_info(self):
        values = {
            "project": str(BASE_DIR),
            "python": f"{PYTHON_EXE} ({'존재함' if PYTHON_EXE.is_file() else '찾을 수 없음'})",
            "server": f"{SERVER_SCRIPT} ({'존재함' if SERVER_SCRIPT.is_file() else '찾을 수 없음'})",
            "env": f"{ENV_PATH} ({'존재함' if ENV_PATH.is_file() else '없음'})",
            "mcp_log": str(get_latest_log_file("mcp_server")),
            "tunnel_log": str(get_latest_tunnel_log_file()),
        }
        for key, value in values.items():
            self.program_values[key].setText(value)

    def open_folder(self, path):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def change_page(self, index):
        self.pages.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setProperty("selected", i == index)
            button.style().unpolish(button)
            button.style().polish(button)

        # Opening Server Management always refreshes MCP and Tunnel status.
        if index == 2 and hasattr(self, "dashboard_refresh_button"):
            self.refresh_dashboard()

    def closeEvent(self, event):
        running_workers = [worker for worker in self._workers if worker.isRunning()]
        if running_workers:
            answer = QMessageBox.question(
                self,
                "작업 진행 중",
                "백그라운드 작업이 진행 중입니다. 작업이 끝날 때까지 기다리고 프로그램을 종료할까요?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            for worker in running_workers:
                worker.wait()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Agent Connector")
    window = AgentConnectorWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
