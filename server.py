
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
from mcp.server.subscriptions import ToolsListChanged
from mcp.server.transport_security import TransportSecuritySettings


BASE_DIR = Path(__file__).parent
AGENTS_DIR = BASE_DIR / "agents"

load_dotenv(BASE_DIR / ".env")

mcp = MCPServer("AgentMarketplace")


class BearerTokenMiddleware:
    """疫꿸퀣??Bearer ?醫뤾쿃 ?癒?뮉 Claude ???뮞??URL ?醫뤾쿃??野꺜??鍮??덈뼄."""

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

        query_string = scope.get("query_string", b"").decode("ascii", errors="ignore")
        query_params = parse_qs(query_string)
        query_token = query_params.get("access_token", [""])[0]

        valid_query = (
            bool(self.claude_token)
            and secrets.compare_digest(query_token, self.claude_token)
        )

        if not (valid_bearer or valid_query):
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

def read_manifest(manifest_path):
    with manifest_path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_agent(agent_id):
    """嚥≪뮇類??癒?뵠?袁る뱜 ???텕筌왖???븍뜄???щ빍??"""

    agent_dir = (AGENTS_DIR / agent_id).resolve()
    manifest_path = agent_dir / "manifest.json"

    if not agent_dir.is_relative_to(AGENTS_DIR.resolve()):
        raise ValueError("??됱뒠??? ??? ?癒?뵠?袁る뱜 野껋럥以??낅빍??")

    if not manifest_path.is_file():
        raise ValueError("鈺곕똻???? ??낅뮉 ?癒?뵠?袁る뱜??낅빍??")

    manifest = read_manifest(manifest_path)

    if manifest.get("id") != agent_id:
        raise ValueError("?癒?뵠?袁る뱜 ID揶쎛 ??깊뒄??? ??녿뮸??덈뼄.")

    entrypoint = Path(manifest["entrypoint"])

    if entrypoint.is_absolute() or ".." in entrypoint.parts:
        raise ValueError("??롢걵????쎈뻬 ???뵬 野껋럥以??낅빍??")

    agent_path = (agent_dir / entrypoint).resolve()

    if not agent_path.is_relative_to(agent_dir):
        raise ValueError("??됱뒠??? ??? ??쎈뻬 ???뵬 野껋럥以??낅빍??")

    if not agent_path.is_file():
        raise ValueError("?癒?뵠?袁る뱜 ??쎈뻬 ???뵬??筌≪뼚??????곷뮸??덈뼄.")

    spec = importlib.util.spec_from_file_location(
        f"agent_{agent_id}", agent_path
    )

    if spec is None or spec.loader is None:
        raise ValueError("?癒?뵠?袁る뱜???븍뜄???????곷뮸??덈뼄.")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return manifest, module


@mcp.tool()
def list_agents() -> str:
    """嚥≪뮇類????쇳뒄???癒?뵠?袁る뱜 筌뤴뫖以??鈺곌퀬???몃빍??"""

    agents = []

    if not AGENTS_DIR.exists():
        return "??쇳뒄???癒?뵠?袁る뱜揶쎛 ??곷뮸??덈뼄."

    for manifest_path in sorted(AGENTS_DIR.glob("*/manifest.json")):
        try:
            manifest = read_manifest(manifest_path)

            agents.append(
                f"ID: {manifest['id']}\n"
                f"??已? {manifest['name']}\n"
                f"??살구: {manifest['description']}"
            )

        except (OSError, json.JSONDecodeError, KeyError):
            continue

    if not agents:
        return "??쇳뒄???癒?뵠?袁る뱜揶쎛 ??곷뮸??덈뼄."

    return "\n\n".join(agents)


def make_agent_tool(agent_id, title, description):
    """揶쏆뮆???癒?뵠?袁る뱜??MCP ?袁㏓럡嚥????????λ땾????밴쉐??몃빍??"""

    def agent_tool(task: str) -> str:
        try:
            manifest, module = load_agent(agent_id)

            if not callable(getattr(module, "run", None)):
                return "?癒?뵠?袁る뱜????쎈뻬 揶쎛?館釉?run ??λ땾揶쎛 ??곷뮸??덈뼄."

            return str(module.run(task))

        except Exception as e:
            return f"?癒?뵠?袁る뱜 ??쎈뻬 ??살첒: {e}"

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
        return "?먯씠?꾪듃 紐⑸줉??媛깆떊?섏뿀?듬땲??"

    return "?먯씠?꾪듃 紐⑸줉??蹂寃??ы빆???놁뒿?덈떎."

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

    # Preserve the previously used Quick Tunnel hostname for existing setups.
    if not configured_hosts:
        configured_hosts = ["integral-sapphire-jamie-nil.trycloudflare.com"]

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


if __name__ == "__main__":
    import sys

    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"

    if transport == "stdio":
        mcp.run(transport="stdio")

    elif transport == "streamable-http":
        token = os.getenv("MCP_AUTH_TOKEN")

        if not token:
            raise RuntimeError(
                ".env ???뵬??MCP_AUTH_TOKEN????쇱젟??? ??녿릭??щ빍??"
            )

        app = mcp.streamable_http_app(host="127.0.0.1", transport_security=build_transport_security())
        app = BearerTokenMiddleware(app, token, os.getenv("CLAUDE_TEST_TOKEN", ""))

        import uvicorn

        uvicorn.run(
            app,
            host="127.0.0.1",
            port=8000,
            log_level="info",
            access_log=False
        )

    else:
        raise ValueError("筌왖?癒곕릭筌왖 ??낅뮉 ?袁⑸꽊 獄쎻뫗???낅빍??")


