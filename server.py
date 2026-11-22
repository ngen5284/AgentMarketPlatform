
import json
import importlib.util
import logging
import re
import os
import secrets
from urllib.parse import parse_qs
from pathlib import Path

from dotenv import load_dotenv
from mcp.server import MCPServer
from mcp.server.auth.routes import create_auth_routes
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from pydantic import AnyHttpUrl
from starlette.routing import Route
from mcp.server.subscriptions import ToolsListChanged
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


def read_manifest(manifest_path):
    with manifest_path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_agent(agent_id):
    """로컬 에이전트 패키지를 불러옵니다."""

    agent_dir = (AGENTS_DIR / agent_id).resolve()
    manifest_path = agent_dir / "manifest.json"

    if not agent_dir.is_relative_to(AGENTS_DIR.resolve()):
        raise ValueError("유효하지 않은 에이전트 경로입니다.")

    if not manifest_path.is_file():
        raise ValueError("존재하지 않는 에이전트입니다.")

    manifest = read_manifest(manifest_path)

    if manifest.get("id") != agent_id:
        raise ValueError("에이전트 ID가 일치하지 않습니다.")

    entrypoint = Path(manifest["entrypoint"])

    if entrypoint.is_absolute() or ".." in entrypoint.parts:
        raise ValueError("잘못된 실행 파일 경로입니다.")

    agent_path = (agent_dir / entrypoint).resolve()

    if not agent_path.is_relative_to(agent_dir):
        raise ValueError("유효하지 않은 실행 파일 경로입니다.")

    if not agent_path.is_file():
        raise ValueError("에이전트 실행 파일을 찾을 수 없습니다.")

    spec = importlib.util.spec_from_file_location(
        f"agent_{agent_id}", agent_path
    )

    if spec is None or spec.loader is None:
        raise ValueError("에이전트를 불러올 수 없습니다.")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return manifest, module


@mcp.tool()
def list_agents() -> str:
    """로컬에 설치된 에이전트 목록을 조회합니다."""

    agents = []

    if not AGENTS_DIR.exists():
        return "설치된 에이전트가 없습니다."

    for manifest_path in sorted(AGENTS_DIR.glob("*/manifest.json")):
        try:
            manifest = read_manifest(manifest_path)

            agents.append(
                f"ID: {manifest['id']}\n"
                f"이름: {manifest['name']}\n"
                f"설명: {manifest['description']}"
            )

        except (OSError, json.JSONDecodeError, KeyError):
            continue

    if not agents:
        return "설치된 에이전트가 없습니다."

    return "\n\n".join(agents)


def make_agent_tool(agent_id, title, description):
    """개별 에이전트를 MCP 도구로 호출할 함수를 생성합니다."""

    def agent_tool(task: str) -> str:
        try:
            manifest, module = load_agent(agent_id)

            if not callable(getattr(module, "run", None)):
                return "에이전트에 실행 가능한 run 함수가 없습니다."

            return str(module.run(task))

        except Exception as e:
            return f"에이전트 실행 오류: {e}"

    agent_tool.__name__ = agent_id
    agent_tool.__doc__ = description

    return agent_tool


registered_agent_tools = set()


def register_agent_tools():
    """Synchronize installed agent packages with MCP tools."""

    current_ids = set()
    added = False

    if AGENTS_DIR.exists():
        for manifest_path in sorted(AGENTS_DIR.glob("*/manifest.json")):
            try:
                manifest = read_manifest(manifest_path)

                agent_id = manifest["id"]
                title = manifest["name"]
                description = manifest["description"]

                if not isinstance(agent_id, str):
                    continue

                if not re.fullmatch(r"[A-Za-z0-9_-]+", agent_id):
                    continue

                if agent_id == "list_agents":
                    continue

                if not isinstance(title, str) or not isinstance(description, str):
                    continue

                current_ids.add(agent_id)

                if agent_id in registered_agent_tools:
                    continue

                tool_fn = make_agent_tool(agent_id, title, description)

                mcp.add_tool(
                    tool_fn,
                    name=agent_id,
                    title=title,
                    description=description
                )

                registered_agent_tools.add(agent_id)
                added = True

            except Exception as e:
                logging.warning(
                    "Agent registration failed (%s): %s",
                    manifest_path.parent.name,
                    e
                )

    removed_ids = registered_agent_tools - current_ids

    for agent_id in removed_ids:
        try:
            mcp.remove_tool(agent_id)
            registered_agent_tools.remove(agent_id)
        except Exception as e:
            logging.warning("Agent removal failed (%s): %s", agent_id, e)

    return added or bool(removed_ids)


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


