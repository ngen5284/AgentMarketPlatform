import asyncio
import os

import httpx2
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env")
MCP_URL = "http://127.0.0.1:8000/mcp"


async def _refresh_server_agents():
    load_dotenv(ENV_PATH)

    token = os.getenv("MCP_AUTH_TOKEN")
    if not token:
        return {
            "success": False,
            "message": ".env에 MCP_AUTH_TOKEN이 설정되어 있지 않습니다.",
        }

    headers = {
        "Authorization": f"Bearer {token}",
    }

    timeout = httpx2.Timeout(30.0, read=None)

    try:
        async with httpx2.AsyncClient(
            headers=headers,
            timeout=timeout,
        ) as http_client:

            async with streamable_http_client(
                MCP_URL,
                http_client=http_client,
            ) as (read_stream, write_stream):

                async with ClientSession(
                    read_stream,
                    write_stream,
                ) as session:

                    await session.initialize()

                    result = await session.call_tool(
                        "refresh_agents",
                        {},
                    )

                    messages = [
                        item.text
                        for item in result.content
                        if hasattr(item, "text")
                    ]

                    if result.is_error:
                        return {
                            "success": False,
                            "message": "\n".join(messages) or "MCP 도구 호출 실패",
                        }

                    return {
                        "success": True,
                        "message": "\n".join(messages) or "에이전트 목록 갱신 요청 성공",
                    }

    except Exception as exc:
        return {
            "success": False,
            "message": f"MCP 서버 연결 또는 호출 실패: {type(exc).__name__}: {exc!r}",
        }


def refresh_server_agents():
    """Synchronize installed agent packages with the running MCP server."""
    return asyncio.run(_refresh_server_agents())



async def _check_server_status():
    """Check MCP server connectivity and retrieve registered tools."""

    load_dotenv(ENV_PATH)

    token = os.getenv("MCP_AUTH_TOKEN")
    if not token:
        return {
            "success": False,
            "message": "MCP_AUTH_TOKEN is not configured.",
            "tools": [],
        }

    headers = {
        "Authorization": f"Bearer {token}",
    }

    timeout = httpx2.Timeout(30.0, read=None)

    try:
        async with httpx2.AsyncClient(
            headers=headers,
            timeout=timeout,
        ) as http_client:

            async with streamable_http_client(
                MCP_URL,
                http_client=http_client,
            ) as (read_stream, write_stream):

                async with ClientSession(
                    read_stream,
                    write_stream,
                ) as session:

                    await session.initialize()
                    result = await session.list_tools()

                    tools = [
                        tool.name
                        for tool in result.tools
                    ]

                    return {
                        "success": True,
                        "message": "MCP server connection successful.",
                        "tools": tools,
                    }

    except Exception as exc:
        return {
            "success": False,
            "message": f"{type(exc).__name__}: {exc!r}",
            "tools": [],
        }


def check_server_status():
    """Check the running MCP server status."""
    return asyncio.run(_check_server_status())
