import json
import re
import shutil
from pathlib import Path

from connector.mcp_client import refresh_server_agents
from connector.integrity import verify_package_integrity
from connector.security import verify_package_security


BASE_DIR = Path(__file__).resolve().parent.parent
AGENTS_DIR = BASE_DIR / "agents"
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def validate_package(package_dir: Path, require_integrity: bool = False) -> dict:
    """Validate package structure and optionally verify file integrity."""

    package_dir = package_dir.resolve()
    manifest_path = package_dir / "manifest.json"

    if not manifest_path.is_file():
        raise ValueError("manifest.json이 없습니다.")

    with manifest_path.open("r", encoding="utf-8-sig") as f:
        manifest = json.load(f)

    if not isinstance(manifest, dict):
        raise ValueError("manifest.json 형식이 올바르지 않습니다.")

    agent_id = manifest.get("id")
    name = manifest.get("name")
    description = manifest.get("description")
    entrypoint = manifest.get("entrypoint")

    if not isinstance(agent_id, str) or not ID_PATTERN.fullmatch(agent_id):
        raise ValueError("잘못된 에이전트 ID입니다.")

    if agent_id == "list_agents":
        raise ValueError("예약된 에이전트 ID입니다.")

    if not isinstance(name, str) or not name.strip():
        raise ValueError("에이전트 이름이 올바르지 않습니다.")

    if not isinstance(description, str):
        raise ValueError("에이전트 설명이 올바르지 않습니다.")

    if not isinstance(entrypoint, str) or not entrypoint.strip():
        raise ValueError("entrypoint가 올바르지 않습니다.")

    entry_path = (package_dir / entrypoint).resolve()

    if not entry_path.is_relative_to(package_dir):
        raise ValueError("entrypoint가 패키지 폴더 외부를 가리킵니다.")

    if not entry_path.is_file():
        raise ValueError("entrypoint 파일이 존재하지 않습니다.")

    if require_integrity:
        security_result = verify_package_security(package_dir)

        if not security_result["success"]:
            raise ValueError(
                f"Package security check failed: {security_result}"
            )

    integrity_path = package_dir / "integrity.json"

    if require_integrity and not integrity_path.is_file():
        raise ValueError("integrity.json이 없는 패키지는 설치할 수 없습니다.")

    if integrity_path.exists():
        if integrity_path.is_symlink():
            raise ValueError("integrity.json은 심볼릭 링크일 수 없습니다.")

        result = verify_package_integrity(package_dir)

        if not result["success"]:
            raise ValueError(
                f"패키지 무결성 검증 실패: {result}"
            )

    return manifest


def _refresh_result() -> dict:
    """Refresh the running MCP server without undoing file operations."""

    try:
        result = refresh_server_agents()
        return {
            "success": bool(result.get("success")),
            "message": result.get("message", ""),
        }
    except Exception as exc:
        return {
            "success": False,
            "message": f"{type(exc).__name__}: {exc}",
        }


def list_agents() -> list[dict]:
    """Return installed agent package information."""

    agents = []

    if not AGENTS_DIR.exists():
        return agents

    for package_dir in sorted(AGENTS_DIR.iterdir()):
        if not package_dir.is_dir():
            continue

        try:
            manifest = validate_package(package_dir)
            agents.append({
                "id": manifest["id"],
                "name": manifest["name"],
                "description": manifest["description"],
                "path": str(package_dir),
            })
        except Exception as exc:
            agents.append({
                "id": package_dir.name,
                "name": "INVALID",
                "description": str(exc),
                "path": str(package_dir),
            })

    return agents


def install_agent(source_dir: str | Path) -> dict:
    """Verify, install a package, recover on failure, and refresh MCP."""

    source_dir = Path(source_dir).resolve()

    if not source_dir.is_dir():
        raise ValueError("??? ??? ??? ???? ????.")

    manifest = validate_package(source_dir, require_integrity=True)
    agent_id = manifest["id"]

    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    target_dir = AGENTS_DIR / agent_id

    if target_dir.exists():
        raise FileExistsError(f"?? ??? ???????: {agent_id}")

    try:
        shutil.copytree(source_dir, target_dir)
        validate_package(target_dir, require_integrity=True)

    except Exception:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        raise

    return {
        "id": agent_id,
        "name": manifest["name"],
        "path": str(target_dir),
        "refresh": _refresh_result(),
    }

def remove_agent(agent_id: str) -> dict:
    """Remove a package and request MCP server refresh."""

    if not isinstance(agent_id, str) or not ID_PATTERN.fullmatch(agent_id):
        raise ValueError("잘못된 에이전트 ID입니다.")

    if agent_id == "list_agents":
        raise ValueError("예약된 에이전트 ID입니다.")

    target_dir = AGENTS_DIR / agent_id

    if not target_dir.is_dir():
        raise FileNotFoundError(f"설치된 에이전트가 없습니다: {agent_id}")

    if target_dir.is_symlink():
        raise ValueError("심볼릭 링크 패키지는 삭제할 수 없습니다.")

    shutil.rmtree(target_dir)

    return {
        "id": agent_id,
        "removed": True,
        "refresh": _refresh_result(),
    }
