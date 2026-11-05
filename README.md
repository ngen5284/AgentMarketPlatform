# Agent Marketplace Connector

Agent Marketplace Connector는 마켓플레이스에서 제공하는 AI 에이전트를 사용자의 PC에서 관리하고 실행하기 위한 Windows용 프로그램입니다.

사용자는 Connector를 통해 에이전트 패키지를 설치하거나 삭제할 수 있으며, 로컬 MCP 서버를 이용해 에이전트의 기능을 외부 AI 서비스와 연결할 수 있습니다.

## 주요 기능

- 에이전트 설치 및 삭제
- 설치된 에이전트 목록과 상태 확인
- 에이전트 도구의 동적 등록 및 갱신
- 로컬 MCP 서버 실행 및 종료
- 서버 연결 상태와 실행 로그 확인
- 에이전트 패키지의 보안 및 무결성 검사
- Cloudflare Tunnel을 이용한 외부 연결 지원

## 프로젝트 구성

`server.py`는 로컬 MCP 서버를 실행합니다.

`connector` 폴더에는 서버 실행 관리, 에이전트 설치 및 삭제, 보안 검사, GUI 등 Connector의 핵심 기능이 들어 있습니다.

`agents` 폴더에는 테스트와 기능 확인에 사용할 수 있는 에이전트 패키지가 들어 있습니다.

## 개발 환경에서 실행하기

현재 프로젝트는 Windows 환경에서 Python 3.12를 기준으로 개발되었습니다.

먼저 프로젝트 폴더에서 필요한 패키지를 설치합니다.

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt

환경변수 설정은 `.env.example`을 참고합니다. 실제 인증 토큰을 사용하는 `.env` 파일은 별도로 만들어야 합니다.

필수 설정:
- `MCP_AUTH_TOKEN`: MCP 서버 인증에 사용하는 토큰

선택 설정:
- `MCP_ALLOWED_HOSTS`: 접속을 허용할 호스트 목록
- `CLAUDE_TEST_TOKEN`: 테스트용 인증 토큰

GUI 실행:

    python -m connector.gui

MCP 서버 직접 실행:

    python server.py streamable-http

기본 MCP 서버 주소:

    http://127.0.0.1:8000/mcp

## 기본 제공 에이전트

- `demo_agent`: 에이전트 패키지 설치와 로딩을 확인하기 위한 테스트 에이전트
- `text_analyzer`: 입력된 텍스트의 글자 수와 단어 수를 분석하는 에이전트
- `refresh_test`: 에이전트 도구의 동적 등록 및 갱신을 확인하기 위한 개발용 테스트 에이전트

`refresh_test`는 기능 검증을 위한 자료이며 일반 사용자용 에이전트와는 구분됩니다.

## 에이전트 패키지

에이전트는 각각 독립된 패키지 형태로 관리합니다.

기본 패키지는 다음 파일로 구성됩니다.

- `manifest.json`: 에이전트의 이름, 설명, 실행 파일 등의 정보
- `agent.py`: 에이전트의 실제 기능을 구현하는 코드
- `integrity.json`: 패키지 파일의 무결성을 확인하기 위한 정보

패키지를 설치할 때 보안 검사와 SHA-256 기반 무결성 검증을 수행합니다.

다만 정적 보안 검사는 위험한 코드 패턴을 탐지하기 위한 것으로, 모든 악성 동작을 차단하거나 실행을 완전히 격리하는 기능은 아닙니다.

## Cloudflare Tunnel

외부에서 로컬 MCP 서버에 연결할 수 있도록 Cloudflare Tunnel을 지원합니다.

개발 환경에서는 다음 위치에 Windows용 Cloudflare 실행 파일이 있어야 합니다.

    tools/cloudflared/cloudflared.exe

Cloudflare 실행 파일은 용량과 배포 관리 문제로 Git 저장소에는 포함하지 않습니다. 실제 설치 프로그램에는 별도로 포함할 예정입니다.

## 개발 및 배포 관련 안내

이 저장소는 Agent Marketplace Connector의 소스 코드와 기본 에이전트 패키지를 관리하기 위한 저장소입니다.

실제 인증 정보, 가상환경, 로그, 실행 상태 파일, 백업 파일 및 빌드 결과물은 저장소에 포함하지 않습니다.

최종 사용자용 설치 프로그램은 별도의 패키징 및 설치 과정을 통해 제작합니다.
