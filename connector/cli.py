import argparse
import json
import sys

from connector.agent_manager import (
    install_agent,
    list_agents,
    remove_agent,
)
from connector.mcp_client import (
    check_server_status,
    refresh_server_agents,
)
from connector.server_manager import (
    start_server,
    stop_server,
    get_process_status,
)


def print_result(result):
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Agent Marketplace Local Connector"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="설치된 에이전트 목록 조회")

    install_parser = subparsers.add_parser(
        "install",
        help="에이전트 패키지 설치",
    )
    install_parser.add_argument("package_path")

    remove_parser = subparsers.add_parser(
        "remove",
        help="설치된 에이전트 삭제",
    )
    remove_parser.add_argument("agent_id")

    subparsers.add_parser("refresh", help="MCP 서버 에이전트 목록 갱신")
    subparsers.add_parser("status", help="MCP 서버 연결 및 도구 상태 확인")

    subparsers.add_parser("start", help="MCP 서버 시작")
    subparsers.add_parser("stop", help="Connector 관리 MCP 서버 종료")
    subparsers.add_parser("process", help="MCP 서버 프로세스 상태 확인")

    args = parser.parse_args()

    try:
        if args.command == "list":
            print_result(list_agents())

        elif args.command == "install":
            print_result(install_agent(args.package_path))

        elif args.command == "remove":
            print_result(remove_agent(args.agent_id))

        elif args.command == "refresh":
            result = refresh_server_agents()
            print_result(result)
            if not result.get("success"):
                sys.exit(1)

        elif args.command == "status":
            result = check_server_status()
            print_result(result)
            if not result.get("success"):
                sys.exit(1)

        elif args.command == "start":
            result = start_server()
            print_result(result)
            if not result.get("success"):
                sys.exit(1)

        elif args.command == "stop":
            result = stop_server()
            print_result(result)
            if not result.get("success"):
                sys.exit(1)

        elif args.command == "process":
            result = get_process_status()
            print_result(result)
            if not result.get("success"):
                sys.exit(1)

    except Exception as exc:
        print(f"오류: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
