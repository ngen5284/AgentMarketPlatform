import json
import re
import shutil
import tempfile
from pathlib import Path

from connector.mcp_client import refresh_server_agents
from connector.integrity import verify_package_integrity
from connector.security import verify_package_security


BASE_DIR = Path(__file__).resolve().parent.parent
AGENTS_DIR = BASE_DIR / "agents"
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
AGENT_JSON_ID_PATTERN = re.compile(r"^[a-z0-9_]{1,64}$")


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



def validate_agent_json(source: str | Path | dict) -> dict:
    if isinstance(source, dict):
        manifest = source
    else:
        source_path = Path(source)
        if not source_path.is_file():
            raise ValueError("agent.json 파일이 존재하지 않습니다.")

        try:
            with source_path.open("r", encoding="utf-8-sig") as file:
                manifest = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"agent.json을 읽을 수 없습니다: {exc}") from exc

    if not isinstance(manifest, dict):
        raise ValueError("agent.json 최상위 값은 JSON 객체여야 합니다.")

    required_fields = (
        "id",
        "agentName",
        "version",
        "description",
        "prompt",
        "inputSchema",
        "outputSchema",
        "requiredTools",
        "browserSupport",
        "mcpSupport",
    )

    missing = [field for field in required_fields if field not in manifest]
    if missing:
        raise ValueError(f"필수 필드가 없습니다: {', '.join(missing)}")

    agent_id = manifest["id"]
    if not isinstance(agent_id, str) or not AGENT_JSON_ID_PATTERN.fullmatch(agent_id):
        raise ValueError("에이전트 ID는 영문 소문자·숫자·밑줄만 사용할 수 있으며 최대 64자입니다.")

    if isinstance(agent_id, str) and agent_id in {"list_agents", "refresh_agents"}:
        raise ValueError("예약된 에이전트 ID입니다.")

    text_fields = {
        "agentName": 100,
        "description": 2000,
        "prompt": 10000,
    }

    for field, max_length in text_fields.items():
        value = manifest[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field}가 비어 있거나 문자열이 아닙니다.")
        if len(value) > max_length:
            raise ValueError(f"{field}의 최대 길이는 {max_length}자입니다.")

    version = manifest["version"]
    if (
        not isinstance(version, str)
        or len(version) > 30
        or not re.fullmatch(r"\d+\.\d+\.\d+", version)
    ):
        raise ValueError("version은 1.0.0과 같은 숫자 3단계 형식이어야 합니다.")

    for field in ("inputSchema", "outputSchema"):
        if not isinstance(manifest[field], dict):
            raise ValueError(f"{field}는 JSON 객체여야 합니다.")

    required_model = manifest.get("requiredModel")
    if required_model is not None and not isinstance(required_model, str):
        raise ValueError("requiredModel은 문자열 또는 null이어야 합니다.")

    required_tools = manifest["requiredTools"]
    if (
        not isinstance(required_tools, list)
        or any(not isinstance(item, str) for item in required_tools)
    ):
        raise ValueError("requiredTools는 문자열 목록이어야 합니다.")

    for field in ("browserSupport", "mcpSupport"):
        if type(manifest[field]) is not bool:
            raise ValueError(f"{field}는 true 또는 false여야 합니다.")

    author = manifest.get("author")
    if author is not None and not isinstance(author, str):
        raise ValueError("author는 문자열 또는 null이어야 합니다.")

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
    """
    agent.json만을 기준으로 설치된 에이전트를 조회합니다.
    manifest.json 기반의 기존 목록 조회는 사용하지 않습니다.
    """

    agents = []

    if not AGENTS_DIR.exists():
        return agents

    for package_dir in sorted(AGENTS_DIR.iterdir()):

        if not package_dir.is_dir():
            continue

        agent_json = package_dir / "agent.json"

        if not agent_json.is_file():
            continue

        try:
            if package_dir.is_symlink() or agent_json.is_symlink():
                raise ValueError(
                    "심볼릭 링크 에이전트 패키지는 허용되지 않습니다."
                )

            manifest = validate_agent_json(agent_json)

            if manifest["id"] != package_dir.name:
                raise ValueError(
                    "agent.json ID와 패키지 폴더명이 일치하지 않습니다."
                )

            agents.append({
                "id": manifest["id"],
                "name": manifest["agentName"],
                "description": manifest["description"],
                "version": manifest["version"],
                "format": "marketplace_json",
                "path": str(package_dir),
            })

        except Exception as exc:
            agents.append({
                "id": package_dir.name,
                "name": "INVALID",
                "description": str(exc),
                "format": "invalid_json",
                "path": str(package_dir),
            })

    return agents



def install_agent(source_file: str | Path) -> dict:
    source_path = Path(source_file).expanduser()

    if source_path.is_dir():
        raise ValueError(
            "기존 Python 패키지 폴더가 아니라 Marketplace에서 받은 agent.json 파일을 선택해야 합니다."
        )

    if source_path.is_symlink():
        raise ValueError("심볼릭 링크 파일은 설치할 수 없습니다.")

    if not source_path.is_file():
        raise ValueError("설치할 agent.json 파일이 존재하지 않습니다.")

    if source_path.suffix.lower() != ".json":
        raise ValueError("JSON 형식의 에이전트 파일만 설치할 수 있습니다.")

    source_path = source_path.resolve(strict=True)
    manifest = validate_agent_json(source_path)

    if not manifest["mcpSupport"]:
        raise ValueError("이 에이전트는 Local MCP 연결을 지원하지 않습니다.")

    agent_id = manifest["id"]

    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    agents_root = AGENTS_DIR.resolve()
    target_dir = agents_root / agent_id

    if target_dir.exists() or target_dir.is_symlink():
        raise FileExistsError(f"이미 설치된 에이전트입니다: {agent_id}")

    staging_dir = None

    try:
        staging_dir = Path(tempfile.mkdtemp(
            prefix=f".{agent_id}.installing-",
            dir=str(agents_root),
        ))

        staged_file = staging_dir / "agent.json"
        shutil.copy2(source_path, staged_file)

        copied_manifest = validate_agent_json(staged_file)

        if copied_manifest["id"] != agent_id:
            raise ValueError("복사된 에이전트 ID가 원본과 일치하지 않습니다.")

        if not copied_manifest["mcpSupport"]:
            raise ValueError("Local MCP를 지원하지 않는 에이전트입니다.")

        staging_dir.rename(target_dir)

    except Exception:
        if staging_dir is not None and staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    # 설치 완료 후 실행 중인 MCP 서버에 에이전트 목록 갱신을 요청합니다.
    refresh_result = _refresh_result()

    return {
        "id": agent_id,
        "name": manifest["agentName"],
        "version": manifest["version"],
        "format": "marketplace_json",
        "path": str(target_dir),
        "refresh": refresh_result,
    }



def remove_agent(agent_id: str) -> dict:
    """Remove a package and request MCP server refresh."""
    if isinstance(agent_id, str) and agent_id in {"list_agents", "refresh_agents"}:
        raise ValueError("예약된 MCP 도구 ID는 삭제할 수 없습니다.")


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
