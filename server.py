
import json
import importlib.util
import logging
import re
import os
import secrets
import hashlib
from copy import deepcopy
from typing import Any
from urllib.parse import parse_qs
from pathlib import Path

from dotenv import load_dotenv
from mcp.server import MCPServer
from mcp.server.auth.routes import create_auth_routes
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from pydantic import AnyHttpUrl, ConfigDict, Field, create_model
from starlette.routing import Route
from mcp.server.subscriptions import ToolsListChanged
from mcp.server.mcpserver.tools.base import Tool as InternalMCPTool
from mcp.server.mcpserver.utilities.func_metadata import ArgModelBase, FuncMetadata
from mcp.server.mcpserver.exceptions import ToolError
from jsonschema.validators import validator_for
from mcp.server.transport_security import TransportSecuritySettings


BASE_DIR = Path(__file__).parent
AGENTS_DIR = BASE_DIR / "agents"

load_dotenv(BASE_DIR / ".env")

OAUTH_SCOPE = "mcp:tools"
MCP_OAUTH_ENABLED = os.getenv("MCP_OAUTH_ENABLED", "false").strip().lower() in {
    "1", "true", "yes", "on"
}

oauth_provider = None
oauth_issuer_url = None
oauth_resource_url = None

if MCP_OAUTH_ENABLED:
    from connector.oauth_server import LocalOAuthProvider, LocalTokenVerifier

    issuer_value = os.getenv("MCP_OAUTH_ISSUER_URL", "").strip()
    resource_value = os.getenv("MCP_OAUTH_RESOURCE_URL", "").strip()
    password_hash = os.getenv("MCP_OAUTH_PASSWORD_HASH", "").strip()

    if not issuer_value or not resource_value or not password_hash:
        raise RuntimeError(
            "OAuth가 활성화되어 있지만 Issuer URL, Resource URL 또는 로그인 비밀번호가 설정되지 않았습니다."
        )

    oauth_issuer_url = AnyHttpUrl(issuer_value)
    oauth_resource_url = AnyHttpUrl(resource_value)

    oauth_provider = LocalOAuthProvider(
        database_path=BASE_DIR / "runtime" / "oauth.sqlite3",
        password_hash=password_hash,
        issuer_url=str(oauth_issuer_url).rstrip("/"),
        resource_url=str(oauth_resource_url).rstrip("/"),
    )

    oauth_verifier = LocalTokenVerifier(
        provider=oauth_provider,
        resource_url=str(oauth_resource_url).rstrip("/"),
        mcp_token=os.getenv("MCP_AUTH_TOKEN", ""),
        claude_token=os.getenv("CLAUDE_TEST_TOKEN", ""),
    )

    oauth_auth_settings = AuthSettings(
        issuer_url=oauth_issuer_url,
        resource_server_url=oauth_resource_url,
        required_scopes=[OAUTH_SCOPE],
        validate_token_resource=True,
    )

    mcp = MCPServer(
        "AgentMarketplace",
        auth=oauth_auth_settings,
        token_verifier=oauth_verifier,
    )
else:
    mcp = MCPServer("AgentMarketplace")


class BearerTokenMiddleware:
    """기본 Bearer 토큰 또는 Claude 테스트용 URL 토큰을 검사합니다."""

    def __init__(self, app, token, claude_token):
        self.app = app
        self.token = token
        self.claude_token = claude_token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode("latin-1")

        scheme, separator, supplied_token = auth_header.partition(" ")

        valid_bearer = (
            separator
            and scheme.lower() == "bearer"
            and secrets.compare_digest(supplied_token, self.token)
        )

        x_auth_token = headers.get(b"x-auth-token", b"").decode("latin-1")

        valid_x_auth_token = (
            bool(x_auth_token)
            and secrets.compare_digest(x_auth_token, self.token)
        )

        query_string = scope.get("query_string", b"").decode("ascii", errors="ignore")
        query_params = parse_qs(query_string)
        query_token = query_params.get("access_token", [""])[0]

        valid_query = (
            bool(self.claude_token)
            and secrets.compare_digest(query_token, self.claude_token)
        )

        if not (valid_bearer or valid_x_auth_token or valid_query):
            body = b'{"error":"Unauthorized"}'

            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"www-authenticate", b"Bearer"),
                ],
            })

            await send({
                "type": "http.response.body",
                "body": body,
            })
            return

        await self.app(scope, receive, send)


class LegacyCredentialNormalizationMiddleware:
    """Preserve the existing x-auth-token and Claude test URL-token inputs."""

    def __init__(self, app, mcp_token, claude_token):
        self.app = app
        self.mcp_token = mcp_token or ""
        self.claude_token = claude_token or ""

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = list(scope.get("headers", []))
        header_map = {key.lower(): value for key, value in headers}

        if b"authorization" not in header_map:
            normalized_token = ""

            x_auth_token = header_map.get(b"x-auth-token", b"").decode("latin-1")
            if (
                self.mcp_token
                and x_auth_token
                and secrets.compare_digest(x_auth_token, self.mcp_token)
            ):
                normalized_token = x_auth_token
            elif self.claude_token:
                query_string = scope.get("query_string", b"").decode(
                    "ascii", errors="ignore"
                )
                query_token = parse_qs(query_string).get("access_token", [""])[0]
                if query_token and secrets.compare_digest(
                    query_token, self.claude_token
                ):
                    normalized_token = query_token

            if normalized_token:
                scope = dict(scope)
                scope["headers"] = headers + [
                    (b"authorization", f"Bearer {normalized_token}".encode("latin-1"))
                ]

        await self.app(scope, receive, send)



# MARKETPLACE_JSON_RUNTIME
# Marketplace agent.json을 MCP 도구로 등록하는 런타임입니다.


class AgentFuncMetadata(FuncMetadata):
    """에이전트 입력 문자열을 임의로 JSON 파싱하지 않는 메타데이터."""

    def pre_parse_json(self, data: dict[str, Any]) -> dict[str, Any]:
        return dict(data)


def read_agent_json(agent_json_path: str | Path) -> dict:
    """설치된 Marketplace agent.json을 안전하게 읽습니다."""

    from connector.agent_manager import validate_agent_json

    agent_json_path = Path(agent_json_path)

    if agent_json_path.is_symlink():
        raise ValueError("agent.json은 심볼릭 링크일 수 없습니다.")

    package_dir = agent_json_path.parent

    if package_dir.is_symlink():
        raise ValueError("에이전트 폴더는 심볼릭 링크일 수 없습니다.")

    agents_root = AGENTS_DIR.resolve()
    resolved_dir = package_dir.resolve()

    if not resolved_dir.is_relative_to(agents_root):
        raise ValueError("유효하지 않은 에이전트 폴더입니다.")

    if agent_json_path.name != "agent.json" or not agent_json_path.is_file():
        raise ValueError("agent.json 파일을 찾을 수 없습니다.")

    manifest = validate_agent_json(agent_json_path)

    if manifest["id"] != package_dir.name:
        raise ValueError("agent.json ID와 설치 폴더명이 일치하지 않습니다.")

    return manifest


def normalize_agent_input_schema(raw_schema: dict) -> dict:
    """
    백엔드 Map 형태의 inputSchema/outputSchema를
    MCP 호환 JSON Schema로 변환합니다.

    지원 형식 1:
        {"text": "string", "count": "integer"}

    지원 형식 2:
        {
            "text": {"type": "string"},
            "count": {"type": "integer", "default": 1}
        }

    지원 형식 3:
        {
            "type": "object",
            "properties": {...},
            "required": [...]
        }
    """

    from copy import deepcopy
    from jsonschema.validators import validator_for

    if not isinstance(raw_schema, dict):
        raise ValueError("Schema는 JSON 객체여야 합니다.")

    is_json_schema = (
        "properties" in raw_schema
        or raw_schema.get("type") == "object"
        or "$schema" in raw_schema
        or "$ref" in raw_schema
    )

    if is_json_schema:
        schema = deepcopy(raw_schema)

        if "properties" in schema and "type" not in schema:
            schema["type"] = "object"

        if schema.get("type") != "object":
            raise ValueError(
                "MCP Schema 최상위 type은 object여야 합니다."
            )

        schema.setdefault("properties", {})

        if not isinstance(schema["properties"], dict):
            raise ValueError(
                "Schema properties는 JSON 객체여야 합니다."
            )

        if "required" not in schema:
            schema["required"] = []

    else:
        properties = {}
        required = []

        for field_name, definition in raw_schema.items():

            if not isinstance(field_name, str) or not field_name:
                raise ValueError(
                    "Schema 필드 이름은 비어 있지 않은 문자열이어야 합니다."
                )

            if isinstance(definition, str):
                properties[field_name] = {
                    "type": definition
                }

                required.append(field_name)

            elif isinstance(definition, dict):
                properties[field_name] = deepcopy(definition)

                if "default" not in definition:
                    required.append(field_name)

            else:
                raise ValueError(
                    f"잘못된 Schema 필드 정의입니다: {field_name}"
                )

        schema = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
            "required": required,
        }

    if not isinstance(schema.get("required", []), list):
        raise ValueError("Schema required는 목록이어야 합니다.")

    validator_class = validator_for(schema)
    validator_class.check_schema(schema)

    return schema



def build_agent_argument_model(agent_id: str, schema: dict) -> type:
    """JSON Schema 속성에 맞는 동적 Pydantic 입력 모델을 만듭니다."""

    properties = schema.get("properties", {})
    required = schema.get("required", [])

    if not isinstance(required, list) or any(
        not isinstance(item, str) for item in required
    ):
        raise ValueError("inputSchema.required는 문자열 목록이어야 합니다.")

    extra_mode = (
        "forbid"
        if schema.get("additionalProperties") is False
        else "allow"
    )

    def model_dump_one_level(self):
        result = {}

        for field_name, field_info in self.__class__.model_fields.items():
            alias = field_info.alias or field_name
            extra = field_info.json_schema_extra or {}

            if (
                field_name in self.model_fields_set
                or extra.get("_marketplace_include_default")
            ):
                result[alias] = getattr(self, field_name)

        if self.model_extra:
            result.update(self.model_extra)

        return result

    safe_id = re.sub(r"[^A-Za-z0-9_]", "_", agent_id)

    dynamic_base = type(
        f"Agent_{safe_id}_ArgumentBase",
        (ArgModelBase,),
        {
            "__module__": __name__,
            "model_config": ConfigDict(
                arbitrary_types_allowed=True,
                extra=extra_mode,
            ),
            "model_dump_one_level": model_dump_one_level,
        },
    )

    field_definitions = {}

    for index, (property_name, property_schema) in enumerate(properties.items()):
        if not isinstance(property_name, str):
            raise ValueError("inputSchema 속성 이름은 문자열이어야 합니다.")

        has_default = (
            isinstance(property_schema, dict)
            and "default" in property_schema
        )

        # JSON Schema의 required가 default보다 우선합니다.
        if property_name in required:
            default_value = ...
            include_default = False
        elif has_default:
            default_value = property_schema["default"]
            include_default = True
        else:
            default_value = None
            include_default = False

        field_definitions[f"field_{index}"] = (
            Any,
            Field(
                default=default_value,
                alias=property_name,
                json_schema_extra={
                    "_marketplace_include_default": include_default
                },
            ),
        )

    return create_model(
        f"Agent_{safe_id}_Arguments",
        __base__=dynamic_base,
        **field_definitions,
    )



# LEGACY_PYTHON_MCP_COMPAT
# 기존 manifest.json + agent.py 패키지를 보존하면서 MCP 도구로 제공합니다.

def _read_legacy_agent_package(package_dir):
    from connector.agent_manager import validate_package

    package_dir = Path(package_dir)

    if package_dir.is_symlink():
        raise ValueError("에이전트 폴더는 심볼릭 링크일 수 없습니다.")

    package_dir = package_dir.resolve(strict=True)
    agents_root = AGENTS_DIR.resolve()

    if not package_dir.is_relative_to(agents_root):
        raise ValueError("에이전트 폴더가 agents 폴더 외부에 있습니다.")

    manifest_path = package_dir / "manifest.json"

    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("manifest.json을 찾을 수 없습니다.")

    manifest = validate_package(
        package_dir,
        require_integrity=False
    )

    if manifest["id"] != package_dir.name:
        raise ValueError("에이전트 ID와 폴더명이 일치하지 않습니다.")

    entrypoint = Path(manifest["entrypoint"])

    if entrypoint.is_absolute() or ".." in entrypoint.parts:
        raise ValueError("잘못된 에이전트 실행 경로입니다.")

    candidate = package_dir / entrypoint

    if candidate.is_symlink():
        raise ValueError("실행 파일은 심볼릭 링크일 수 없습니다.")

    entry_path = candidate.resolve(strict=True)

    if not entry_path.is_relative_to(package_dir):
        raise ValueError("실행 파일이 패키지 폴더 외부에 있습니다.")

    if not entry_path.is_file():
        raise ValueError("에이전트 실행 파일이 없습니다.")

    return manifest, entry_path


def _legacy_package_fingerprint(package_dir):
    package_dir = Path(package_dir).resolve()
    digest = hashlib.sha256()

    files = sorted(package_dir.rglob("*"))

    for item in files:
        if item.is_symlink():
            raise ValueError("패키지에 심볼릭 링크가 있습니다.")

        if not item.is_file():
            continue

        relative = item.relative_to(package_dir)

        if "__pycache__" in relative.parts or item.suffix == ".pyc":
            continue

        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.read_bytes())

    return digest.hexdigest()


def _load_legacy_agent_module(agent_id):
    if not isinstance(agent_id, str):
        raise ValueError("에이전트 ID가 올바르지 않습니다.")

    if not re.fullmatch(r"[A-Za-z0-9_-]+", agent_id):
        raise ValueError("잘못된 에이전트 ID입니다.")

    package_dir = AGENTS_DIR / agent_id

    manifest, entry_path = _read_legacy_agent_package(package_dir)

    module_name = "legacy_agent_" + agent_id.replace("-", "_")

    spec = importlib.util.spec_from_file_location(
        module_name,
        str(entry_path)
    )

    if spec is None or spec.loader is None:
        raise ValueError("에이전트 모듈을 불러올 수 없습니다.")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return manifest, module


def make_legacy_agent_tool(agent_id, description):
    def agent_tool(task: str) -> str:
        try:
            manifest, module = _load_legacy_agent_module(agent_id)

            run_function = getattr(module, "run", None)

            if not callable(run_function):
                raise ValueError("실행 가능한 run 함수가 없습니다.")

            return str(run_function(task))

        except Exception as exc:
            logging.exception(
                "Legacy agent execution failed (%s)",
                agent_id
            )
            return f"에이전트 실행 오류: {type(exc).__name__}: {exc}"

    agent_tool.__name__ = agent_id
    agent_tool.__doc__ = description

    return agent_tool


registered_legacy_agent_tools: dict[str, str] = {}


def _register_legacy_agent_tools():
    current_ids = set()
    changed = False

    if not AGENTS_DIR.exists():
        return False

    for package_dir in sorted(AGENTS_DIR.iterdir()):
        if not package_dir.is_dir():
            continue

        agent_json_path = package_dir / "agent.json"

        # 신규 Marketplace JSON 패키지는 기존 등록 로직에 맡깁니다.
        if agent_json_path.is_file():
            continue

        manifest_path = package_dir / "manifest.json"

        if not manifest_path.is_file():
            continue

        try:
            manifest, entry_path = _read_legacy_agent_package(
                package_dir
            )

            agent_id = manifest["id"]
            title = manifest["name"]
            description = manifest["description"]

            if agent_id in {"list_agents", "refresh_agents"}:
                continue

            # JSON 런타임이 같은 ID를 이미 소유하고 있으면 건드리지 않습니다.
            if agent_id in registered_agent_tools:
                continue

            fingerprint = _legacy_package_fingerprint(package_dir)

            existing_tool = mcp._tool_manager.get_tool(agent_id)

            if (
                existing_tool is not None
                and agent_id not in registered_legacy_agent_tools
            ):
                logging.warning(
                    "Legacy Agent tool ID conflict: %s",
                    agent_id
                )
                continue

            current_ids.add(agent_id)

            if (
                registered_legacy_agent_tools.get(agent_id) == fingerprint
                and existing_tool is not None
            ):
                continue

            if agent_id in registered_legacy_agent_tools:
                mcp.remove_tool(agent_id)
                registered_legacy_agent_tools.pop(agent_id, None)

            tool_function = make_legacy_agent_tool(
                agent_id,
                description
            )

            mcp.add_tool(
                tool_function,
                name=agent_id,
                title=title,
                description=description
            )

            registered_legacy_agent_tools[agent_id] = fingerprint
            changed = True

        except Exception as exc:
            logging.warning(
                "Legacy Agent registration failed (%s): %s",
                package_dir.name,
                exc
            )

    removed_ids = set(registered_legacy_agent_tools) - current_ids

    for agent_id in removed_ids:
        try:
            mcp.remove_tool(agent_id)
            registered_legacy_agent_tools.pop(agent_id, None)
            changed = True

        except Exception as exc:
            logging.warning(
                "Legacy Agent removal failed (%s): %s",
                agent_id,
                exc
            )

    return changed


@mcp.tool()
def list_agents() -> str:
    """설치된 Marketplace 및 기존 Python 에이전트 목록을 조회합니다."""

    agents = []

    if not AGENTS_DIR.exists():
        return "설치된 에이전트가 없습니다."

    for package_dir in sorted(AGENTS_DIR.iterdir()):
        if not package_dir.is_dir():
            continue

        agent_json_path = package_dir / "agent.json"

        if agent_json_path.is_file():
            try:
                manifest = read_agent_json(agent_json_path)

                agents.append(
                    f"ID: {manifest['id']}\n"
                    f"이름: {manifest['agentName']}\n"
                    f"버전: {manifest['version']}\n"
                    f"설명: {manifest['description']}"
                )

            except Exception as exc:
                logging.warning(
                    "Marketplace agent listing failed (%s): %s",
                    package_dir.name,
                    exc
                )

            continue

        if not (package_dir / "manifest.json").is_file():
            continue

        try:
            manifest, entry_path = _read_legacy_agent_package(package_dir)

            agents.append(
                f"ID: {manifest['id']}\n"
                f"이름: {manifest['name']}\n"
                f"설명: {manifest['description']}\n"
                f"형식: 기존 Python 패키지"
            )

        except Exception as exc:
            logging.warning(
                "Legacy agent listing failed (%s): %s",
                package_dir.name,
                exc
            )

    if not agents:
        return "설치된 에이전트가 없습니다."

    return "\n\n".join(agents)


def make_agent_tool(manifest: dict, input_schema: dict, input_validator):
    """
    두 가지 실행 경로를 처리합니다.

    1. 로컬 내장 에이전트:
       SHA-256으로 확인된 agent.py를 실제 실행합니다.

    2. Marketplace에서 가져온 일반 agent.json:
       prompt, input, outputSchema를 외부 상용 LLM에 전달합니다.
    """

    import asyncio
    import hashlib
    import importlib.util as importlib_util
    import inspect
    import json
    import sys

    agent_id = manifest["id"]

    local_runtime_hashes = {
    "demo_agent": "1e203f375394e16bcb85c62c043320b4cf00d5e72e0652bfeac9f52a4ad249ec",
    "refresh_test": "58a829aa66ca285f35d5c50ed619b7ae8b03503f89d425cd6bd415b39b68962b",
    "text_analyzer": "88e0f26766a2b0f1fd1165340c613b7b4719b765474fb71808d84f7dd8cf2472"
}

    output_schema = normalize_agent_input_schema(
        manifest["outputSchema"]
    )

    output_validator_class = __import__(
        "jsonschema.validators",
        fromlist=["validator_for"],
    ).validator_for(output_schema)

    output_validator = output_validator_class(
        output_schema
    )

    local_module_cache = {}

    async def agent_tool(**arguments):

        try:
            input_validator.validate(arguments)

        except Exception as exc:
            raise ToolError(
                f"입력값이 inputSchema와 일치하지 않습니다: {exc}"
            ) from exc

        expected_hash = local_runtime_hashes.get(agent_id)

        # ----------------------------------------------------
        # 로컬 내장 에이전트 실행
        # ----------------------------------------------------

        if expected_hash is not None:

            package_dir = (AGENTS_DIR / agent_id).resolve()
            agents_root = AGENTS_DIR.resolve()

            if not package_dir.is_relative_to(agents_root):
                raise ToolError(
                    "유효하지 않은 로컬 에이전트 경로입니다."
                )

            agent_file = package_dir / "agent.py"

            if not agent_file.is_file():
                raise ToolError(
                    f"로컬 에이전트 실행 파일이 없습니다: {agent_id}"
                )

            actual_hash = hashlib.sha256(
                agent_file.read_bytes()
            ).hexdigest()

            if actual_hash != expected_hash:
                raise ToolError(
                    f"로컬 에이전트 무결성 검증 실패: {agent_id}"
                )

            try:
                module = local_module_cache.get(agent_id)

                if module is None:

                    module_name = (
                        f"_agent_marketplace_local_{agent_id}"
                    )

                    spec = importlib_util.spec_from_file_location(
                        module_name,
                        agent_file,
                    )

                    if spec is None or spec.loader is None:
                        raise RuntimeError(
                            "로컬 에이전트 모듈을 불러올 수 없습니다."
                        )

                    module = importlib_util.module_from_spec(spec)

                    sys.modules[module_name] = module

                    try:
                        spec.loader.exec_module(module)
                    except Exception:
                        sys.modules.pop(module_name, None)
                        raise

                    local_module_cache[agent_id] = module

                run_function = getattr(module, "run", None)

                if not callable(run_function):
                    raise RuntimeError(
                        "agent.py에 실행 가능한 run() 함수가 없습니다."
                    )

                signature = inspect.signature(run_function)

                # 필수 인자 누락 및 허용되지 않은 인자를 검사합니다.
                signature.bind(**arguments)

                result = run_function(**arguments)

                if inspect.isawaitable(result):
                    result = await result

                # 로컬 에이전트의 반환값을 outputSchema로 검사합니다.
                if isinstance(result, dict):
                    output_value = result

                elif (
                    len(output_schema.get("properties", {})) == 1
                ):
                    output_field = next(
                        iter(output_schema["properties"])
                    )

                    output_value = {
                        output_field: result
                    }

                else:
                    output_value = result

                try:
                    output_validator.validate(output_value)

                except Exception as exc:
                    raise RuntimeError(
                        "로컬 에이전트 반환값이 outputSchema와 "
                        f"일치하지 않습니다: {exc}"
                    ) from exc

                if isinstance(result, str):
                    return result

                try:
                    return json.dumps(
                        result,
                        ensure_ascii=False,
                        indent=2,
                    )
                except TypeError:
                    return str(result)

            except ToolError:
                raise

            except Exception as exc:
                raise ToolError(
                    f"로컬 에이전트 실행 실패 ({agent_id}): "
                    f"{type(exc).__name__}: {exc}"
                ) from exc

        # ----------------------------------------------------
        # Marketplace JSON 에이전트 실행 정보 전달
        # ----------------------------------------------------

        response = {
            "agent": {
                "id": manifest["id"],
                "agentName": manifest["agentName"],
                "version": manifest["version"],
                "description": manifest["description"],
                "author": manifest.get("author"),
            },
            "prompt": manifest["prompt"],
            "input": arguments,
            "inputSchema": manifest["inputSchema"],
            "outputSchema": manifest["outputSchema"],
            "requiredModel": manifest.get("requiredModel"),
            "requiredTools": manifest.get("requiredTools", []),
            "browserSupport": manifest["browserSupport"],
            "mcpSupport": manifest["mcpSupport"],
            "executionNote": (
                "prompt를 작업 지침으로 사용하고 input을 작업 데이터로 "
                "사용하십시오. 최종 결과는 outputSchema에 맞추십시오."
            ),
        }

        return json.dumps(
            response,
            ensure_ascii=False,
            indent=2,
        )

    agent_tool.__name__ = agent_id
    agent_tool.__doc__ = manifest["description"]

    return agent_tool



registered_agent_tools: dict[str, str] = {}


def _register_marketplace_json_agent_tools():
    """설치된 Marketplace JSON 에이전트를 MCP 도구와 동기화합니다."""

    current_ids = set()
    changed = False

    if AGENTS_DIR.exists():
        for agent_json_path in sorted(AGENTS_DIR.glob("*/agent.json")):
            try:
                manifest = read_agent_json(agent_json_path)

                agent_id = manifest["id"]

                if isinstance(agent_id, str) and agent_id in {"list_agents", "refresh_agents"}:
                    continue

                if not manifest["mcpSupport"]:
                    continue

                input_schema = normalize_agent_input_schema(
                    manifest["inputSchema"]
                )

                validator_class = validator_for(input_schema)
                input_validator = validator_class(input_schema)

                argument_model = build_agent_argument_model(
                    agent_id,
                    input_schema,
                )

                file_hash = hashlib.sha256(
                    agent_json_path.read_bytes()
                ).hexdigest()

                current_ids.add(agent_id)

                if registered_agent_tools.get(agent_id) == file_hash:
                    continue

                existing_tool = mcp._tool_manager.get_tool(agent_id)

                if (
                    existing_tool is not None
                    and agent_id not in registered_agent_tools
                ):
                    logging.warning(
                        "Agent tool ID conflicts with an existing MCP tool: %s",
                        agent_id,
                    )
                    current_ids.discard(agent_id)
                    continue

                if agent_id in registered_agent_tools:
                    mcp.remove_tool(agent_id)
                    registered_agent_tools.pop(agent_id, None)

                tool_function = make_agent_tool(
                    manifest,
                    input_schema,
                    input_validator,
                )

                dynamic_tool = InternalMCPTool(
                    fn=tool_function,
                    name=agent_id,
                    title=manifest["agentName"],
                    description=manifest["description"],
                    parameters=input_schema,
                    fn_metadata=AgentFuncMetadata(
                        arg_model=argument_model
                    ),
                    is_async=True,
                    context_kwarg=None,
                )

                # MCP SDK의 ToolManager에 동적 Tool 객체를 등록합니다.
                mcp._tool_manager._tools[agent_id] = dynamic_tool

                registered_agent_tools[agent_id] = file_hash
                changed = True

            except Exception as exc:
                logging.warning(
                    "Marketplace Agent 등록 실패 (%s): %s",
                    agent_json_path.parent.name,
                    exc,
                )

    removed_ids = set(registered_agent_tools) - current_ids

    for agent_id in removed_ids:
        try:
            mcp.remove_tool(agent_id)
            registered_agent_tools.pop(agent_id, None)
            changed = True
        except Exception as exc:
            logging.warning(
                "Marketplace Agent 도구 제거 실패 (%s): %s",
                agent_id,
                exc,
            )

    return changed


def register_agent_tools():
    # 기존 Python 패키지를 먼저 등록합니다.
    changed = _register_legacy_agent_tools()

    # 신규 Marketplace agent.json 등록 로직은 그대로 사용합니다.
    changed = _register_marketplace_json_agent_tools() or changed

    # 패키지 형식이 변경된 경우에도 한 번의 갱신으로 정리합니다.
    changed = _register_legacy_agent_tools() or changed

    return changed


register_agent_tools()


async def notify_tools_changed():

    await mcp._subscriptions.publish(ToolsListChanged())


@mcp.tool()
async def refresh_agents() -> str:
    changed = register_agent_tools()

    if changed:
        await notify_tools_changed()
        return "에이전트 목록이 갱신되었습니다."

    return "에이전트 목록에 변경 사항이 없습니다."

def build_transport_security():
    """Build a strict Host/Origin allowlist for localhost and the current Quick Tunnel."""
    allowed_hosts = ["127.0.0.1:8000", "localhost:8000"]
    allowed_origins = [
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ]

    configured_hosts = [
        item.strip().lower()
        for item in os.getenv("MCP_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    ]

    for host in configured_hosts:
        if not re.fullmatch(
            r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.trycloudflare\.com",
            host,
        ):
            logging.warning("Ignoring invalid MCP_ALLOWED_HOSTS entry: %s", host)
            continue

        # The MCP SDK matches exact host names and supports :* for arbitrary ports.
        allowed_hosts.extend([host, f"{host}:*"])
        allowed_origins.extend([f"https://{host}", f"https://{host}:*"])

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(dict.fromkeys(allowed_hosts)),
        allowed_origins=list(dict.fromkeys(allowed_origins)),
    )


if MCP_OAUTH_ENABLED:
    from mcp.server.auth.handlers import revoke as mcp_revoke

    class CompatibleRevocationRequest(mcp_revoke.RevocationRequest):
        client_secret: str | None = None

    mcp_revoke.RevocationRequest = CompatibleRevocationRequest

if __name__ == "__main__":
    import sys

    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"

    if transport == "stdio":
        mcp.run(transport="stdio")

    elif transport == "streamable-http":
        token = os.getenv("MCP_AUTH_TOKEN")

        if not token:
            raise RuntimeError(
                ".env 파일에 MCP_AUTH_TOKEN이 설정되어 있지 않습니다."
            )

        mcp_app = mcp.streamable_http_app(
            host="127.0.0.1",
            transport_security=build_transport_security(),
        )

        if MCP_OAUTH_ENABLED:
            oauth_routes = create_auth_routes(
                provider=oauth_provider,
                issuer_url=oauth_issuer_url,
                client_registration_options=ClientRegistrationOptions(
                    enabled=True,
                    valid_scopes=[OAUTH_SCOPE, "offline_access"],
                    default_scopes=[OAUTH_SCOPE],
                ),
                revocation_options=RevocationOptions(enabled=True),
            )

            oauth_routes.extend([
                Route(
                    "/oauth/login",
                    endpoint=oauth_provider.login_page,
                    methods=["GET"],
                ),
                Route(
                    "/oauth/login/callback",
                    endpoint=oauth_provider.login_callback,
                    methods=["POST"],
                ),
            ])

            # Keep the original MCP Starlette app and its lifespan.
            mcp_app.router.routes = oauth_routes + mcp_app.router.routes
            app = LegacyCredentialNormalizationMiddleware(
                mcp_app,
                token,
                os.getenv("CLAUDE_TEST_TOKEN", ""),
            )
        else:
            app = BearerTokenMiddleware(
                mcp_app,
                token,
                os.getenv("CLAUDE_TEST_TOKEN", ""),
            )

        import uvicorn

        uvicorn.run(
            app,
            host="127.0.0.1",
            port=8000,
            log_level="info",
            access_log=False
        )

    else:
        raise ValueError("지원하지 않는 전송 방식입니다.")


