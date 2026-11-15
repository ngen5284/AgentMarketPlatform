# AI Agent Marketplace Backend

AI Agent를 등록하고 조회, 검색, 수정, 삭제하며 실행 정보가 담긴 `agent.json`을 다운로드할 수 있는 캡스톤 프로젝트용 MVP 백엔드입니다.

현재 범위는 Agent 관리 REST API, MySQL 연동, MCP 지원 Agent 목록 조회입니다. 인증, 실제 Agent 실행, Local MCP Server, LLM, 결제 기능은 포함하지 않습니다.

## 기술 스택

- Java 21
- Spring Boot 4.1.2
- Gradle 9.8.2 (Groovy DSL, Gradle Wrapper 포함)
- Spring Web / Spring Data JPA / Spring Validation
- MySQL (개발 및 실제 동작 확인용)
- H2 (자동 테스트 전용)
- JUnit 6 / Spring Boot Test / MockMvc
- JSON: Spring Boot 4 기본 Jackson 3

Spring Boot 4에서는 MVC 테스트 지원이 별도 모듈로 분리되어 있으므로 `spring-boot-starter-webmvc-test`를 테스트 범위에서 함께 사용합니다.

## 프로젝트 구조

```text
.
├── build.gradle
├── settings.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
├── src/
│   ├── main/
│   │   ├── java/com/agentmarket/backend/
│   │   │   ├── AgentMarketBackendApplication.java
│   │   │   ├── controller/
│   │   │   ├── dto/
│   │   │   ├── entity/
│   │   │   ├── exception/
│   │   │   ├── repository/
│   │   │   └── service/
│   │   └── resources/
│   │       ├── application.yml
│   │       └── application-mysql.yml
│   └── test/
│       ├── java/com/agentmarket/backend/
│       └── resources/application-test.yml
├── .gitignore
└── README.md
```

### 패키지 역할

- `controller`: Agent REST API, MCP 지원 목록 API, 다운로드 헤더 처리
- `service`: CRUD, 중복 검사, DTO 변환, Schema JSON 직렬화/역직렬화
- `repository`: JPA 데이터 접근, 키워드 검색, MCP 지원 여부 조회
- `entity`: `agents`, `agent_required_tools` 테이블 매핑
- `dto`: 등록/수정 요청, 목록 요약 응답, 상세 응답, 다운로드 Package 응답
- `exception`: 예외 클래스와 공통 오류 응답 처리

Entity는 API에 직접 노출하지 않습니다. `inputSchema`와 `outputSchema`는 API에서 JSON Object로 전달되고, DB의 TEXT 컬럼에는 JSON 문자열로 저장됩니다. `requiredTools`는 JPA `@ElementCollection`으로 별도 테이블에 저장됩니다.

## MySQL 준비

사용할 데이터베이스 이름은 반드시 `agent_marketplace`입니다.

```sql
CREATE DATABASE IF NOT EXISTS agent_marketplace
CHARACTER SET utf8mb4;
```

개발 초기에는 Hibernate `ddl-auto=update`를 사용하며, 데이터베이스 구조가 안정된 후 Flyway 등의 마이그레이션 도구 도입을 검토한다.

### 환경변수 설정 (Windows PowerShell)

아래 비밀번호는 형식 설명을 위한 가짜 예시입니다. 실제 MySQL 비밀번호로 바꾸어야 하며 소스코드나 Git에 저장하지 마세요.

```powershell
$env:DB_URL="jdbc:mysql://localhost:3306/agent_marketplace"
$env:DB_USERNAME="root"
$env:DB_PASSWORD="가짜-예시-비밀번호"
```

- `DB_URL` 기본값: `jdbc:mysql://localhost:3306/agent_marketplace`
- `DB_USERNAME` 기본값: `root`
- `DB_PASSWORD`: 기본값이 없으며 반드시 환경에서 제공해야 합니다.

`DB_PASSWORD`가 설정되지 않았거나 MySQL 서버/DB/계정 권한이 준비되지 않으면 MySQL 프로필 실행이 실패할 수 있습니다.

## 실행 및 빌드

모든 명령은 프로젝트 루트에서 실행합니다. 시스템 Gradle 설치는 필요하지 않습니다.

### MySQL 프로필로 실행

H2는 테스트 전용이므로 일반 Spring Boot 실행에는 MySQL 프로필이 필요합니다. `application.yml`에서 프로필을 강제로 활성화하지 않으며 실행 환경에서 직접 `mysql` 프로필을 지정합니다.

```powershell
$env:DB_USERNAME="root"
$env:DB_PASSWORD="실제 MySQL 비밀번호"
.\gradlew.bat bootRun --args="--spring.profiles.active=mysql"
```

서버 기본 주소는 `http://localhost:8080`입니다.

IntelliJ 또는 VS Code의 Run 기능을 사용할 때도 실행 구성의 Active profiles 또는 Program arguments에서 `spring.profiles.active=mysql`을 활성화해야 합니다. 예를 들어 Program arguments에는 `--spring.profiles.active=mysql`을 지정할 수 있습니다.

`DB_PASSWORD`에 기본값이 없으므로 환경변수를 설정하지 않은 상태에서 MySQL 실행이 실패하는 것은 정상입니다.

### 빌드

```powershell
.\gradlew.bat clean build
```

### 테스트

```powershell
.\gradlew.bat test
```

자동 테스트에는 `test` 프로필과 메모리 H2 DB만 사용합니다. H2는 실제 서비스 DB가 아니며 Spring Context 및 자동화된 API 테스트를 MySQL 서버 없이 실행하기 위한 용도입니다. H2의 동작이 MySQL과 완전히 같다고 가정하면 안 되므로 최종 CRUD 확인은 MySQL에서도 수행해야 합니다.

## REST API

| Method | 경로 | 설명 | 성공 상태 |
|---|---|---|---|
| `GET` | `/api/agents` | 전체 목록 | `200 OK` |
| `GET` | `/api/agents?keyword=분석` | 이름/설명 검색 | `200 OK` |
| `GET` | `/api/agents/{id}` | 상세 조회 | `200 OK` |
| `POST` | `/api/agents` | Agent 등록 | `201 Created` |
| `PUT` | `/api/agents/{id}` | Agent 수정 (`id` 변경 불가) | `200 OK` |
| `DELETE` | `/api/agents/{id}` | Agent 삭제 | `204 No Content` |
| `GET` | `/api/agents/{id}/download` | `agent.json` 다운로드 | `200 OK` |
| `GET` | `/api/mcp/agents` | MCP 지원 Agent 목록 | `200 OK` |

### 등록 요청 예시

`author`, `createdAt`, `updatedAt`은 요청에서 받지 않습니다. `author`는 서버가 `anonymous`로 저장하고 시간은 JPA lifecycle로 생성합니다.

```http
POST /api/agents
Content-Type: application/json
```

```json
{
  "id": "text_analyzer",
  "agentName": "텍스트 분석 에이전트",
  "version": "1.0.0",
  "description": "텍스트의 핵심 내용을 분석합니다.",
  "prompt": "입력된 텍스트를 분석하고 요약하세요.",
  "inputSchema": {
    "text": "string",
    "language": "string"
  },
  "outputSchema": {
    "summary": "string",
    "score": "number"
  },
  "requiredModel": "text-generation",
  "requiredTools": [
    "file_reader"
  ],
  "browserSupport": true,
  "mcpSupport": false
}
```

`requiredTools`를 생략하거나 `null`로 보내면 빈 배열로 저장·응답합니다.

### 등록/상세 응답 예시

```json
{
  "id": "text_analyzer",
  "agentName": "텍스트 분석 에이전트",
  "version": "1.0.0",
  "description": "텍스트의 핵심 내용을 분석합니다.",
  "prompt": "입력된 텍스트를 분석하고 요약하세요.",
  "inputSchema": {
    "text": "string",
    "language": "string"
  },
  "outputSchema": {
    "summary": "string",
    "score": "number"
  },
  "requiredModel": "text-generation",
  "requiredTools": [
    "file_reader"
  ],
  "browserSupport": true,
  "mcpSupport": false,
  "author": "anonymous",
  "createdAt": "2026-11-05T20:30:00",
  "updatedAt": "2026-11-05T20:30:00"
}
```

### 목록 및 검색 응답 예시

```http
GET /api/agents?keyword=분석
```

```json
[
  {
    "id": "text_analyzer",
    "agentName": "텍스트 분석 에이전트",
    "version": "1.0.0",
    "description": "텍스트의 핵심 내용을 분석합니다.",
    "browserSupport": true,
    "mcpSupport": false,
    "author": "anonymous",
    "updatedAt": "2026-11-05T20:30:00"
  }
]
```

목록과 검색은 `AgentSummaryResponse`를 사용하므로 `prompt`, Schema, Model, Tool, `createdAt` 같은 상세 정보는 포함하지 않습니다. `keyword`가 없거나 공백이면 전체 목록을 반환합니다. 값이 있으면 `agentName` 또는 `description`에 포함된 문자열을 대소문자 구분 없이 검색합니다.

### 수정 요청/응답 예시

수정 요청에는 `id`가 없습니다. URL 경로의 기존 ID는 바뀌지 않습니다.

```http
PUT /api/agents/text_analyzer
Content-Type: application/json
```

```json
{
  "agentName": "텍스트 분석 Agent 2",
  "version": "1.1.0",
  "description": "수정된 설명입니다.",
  "prompt": "텍스트를 더 자세히 분석하세요.",
  "inputSchema": { "text": "string" },
  "outputSchema": { "summary": "string", "score": "number" },
  "requiredModel": null,
  "requiredTools": [],
  "browserSupport": true,
  "mcpSupport": false
}
```

응답은 상세 응답과 같은 구조이며 `id`와 `createdAt`은 유지되고 `updatedAt`은 서버가 갱신합니다.

### 삭제 응답

```http
DELETE /api/agents/text_analyzer
```

성공하면 본문 없이 `204 No Content`를 반환합니다.

## Agent Package 다운로드

브라우저 또는 HTTP 클라이언트에서 다음 주소를 요청합니다.

```http
GET /api/agents/text_analyzer/download
```

응답은 `Content-Type: application/json`과 `Content-Disposition: attachment; filename="agent.json"`을 사용합니다.

```json
{
  "id": "text_analyzer",
  "agentName": "텍스트 분석 에이전트",
  "version": "1.0.0",
  "description": "텍스트의 핵심 내용을 분석합니다.",
  "prompt": "입력된 텍스트를 분석하고 요약하세요.",
  "inputSchema": { "text": "string" },
  "outputSchema": { "summary": "string" },
  "requiredModel": null,
  "requiredTools": [],
  "browserSupport": true,
  "mcpSupport": false,
  "author": "anonymous"
}
```

실행에 필요하지 않은 `createdAt`, `updatedAt`은 Package에서 제외됩니다. 현재는 ZIP이 아니라 `agent.json` 한 파일만 제공합니다.

### 공통 Agent Package 규격

Browser Runtime과 Local MCP Server는 서로 다른 Package를 사용하지 않고 동일한 `agent.json`을 사용합니다. 현재 구현은 JSON 파일 하나만 제공하며 ZIP, `prompt.txt`, `resources/`는 아직 구현하지 않았습니다.

향후 확장 후보는 다음과 같습니다.

```text
agent-package/
├── agent.json
├── prompt.txt
└── resources/
```

### JSON 입력·출력과 실행 메타데이터

- Agent 입력과 출력은 JSON 형식을 사용합니다.
- `inputSchema`와 `outputSchema`는 `Map<String, Object>`로 받고 응답하며 DB에는 JSON 문자열을 TEXT로 저장합니다.
- `requiredModel`은 필요한 모델 조건을 표현하는 선택 문자열이며 실제 모델을 다운로드하거나 실행하지 않습니다.
- `requiredTools`는 실행에 필요한 Tool 이름 목록이며 없으면 `[]`를 사용합니다.
- `browserSupport`는 Browser Runtime 지원 여부, `mcpSupport`는 Local MCP 환경 지원 여부입니다.

Agent ID는 등록자가 직접 입력하는 최대 64자의 문자열입니다. 영문 소문자, 숫자, 언더바만 허용하며 등록 후 변경할 수 없습니다. 버전은 최대 30자의 `숫자.숫자.숫자` 형식이며 현재 버전 하나만 저장합니다.

## MCP 지원 Agent 목록

```http
GET /api/mcp/agents
```

`mcpSupport == true`인 Agent만 `AgentSummaryResponse` 배열로 반환합니다. 이 API는 향후 Local MCP Server가 사용할 조회 API일 뿐, Local MCP Server 자체나 동기화·Tool 실행 기능은 포함하지 않습니다.

```json
[
  {
    "id": "mcp_agent",
    "agentName": "MCP 지원 에이전트",
    "version": "1.0.0",
    "description": "MCP 환경에서 사용할 수 있습니다.",
    "browserSupport": true,
    "mcpSupport": true,
    "author": "anonymous",
    "updatedAt": "2026-11-06T10:00:00"
  }
]
```

### Local MCP 연결 방향

```text
Marketplace Server
        ↓
Local MCP Server가 MCP 지원 Agent 목록 조회
        ↓
사용자가 Agent 선택
        ↓
Agent Package(agent.json) 다운로드
        ↓
Local MCP Server가 agent.json 읽기
        ↓
Local MCP Tool 등록
        ↓
Claude Desktop 등 MCP Client에서 사용
```

Marketplace Server가 사용자 PC에 파일을 직접 밀어 넣지 않습니다. 향후 Local MCP Server가 Marketplace에서 필요한 Agent를 가져오는 구조로 개발합니다.

### Browser Runtime 연결 방향

Browser Runtime도 동일한 `agent.json`을 사용하며 별도 Browser 전용 Package는 만들지 않습니다. Runtime은 `browserSupport == true`인지 확인한 뒤 `id`, `version`, `prompt`, Schema, Model, Tool 정보를 사용할 예정입니다. 실제 Browser Runtime과 LLM 실행은 현재 백엔드에 포함하지 않습니다.

### Workflow 연결 방향

향후 앞 Agent의 output JSON을 다음 Agent의 input JSON으로 전달하는 순차 실행을 고려합니다.

```text
사용자 입력
↓
요구사항 분석 Agent
↓
기술 추천 Agent
↓
오픈소스 탐색 Agent
↓
개발 계획 Agent
↓
최종 결과
```

현재 백엔드는 Workflow를 실행하지 않고 Agent 정보와 Package만 제공합니다.

## Validation과 오류 응답

- `id`: 필수, 최대 64자, `^[a-z0-9_]+$`, 등록 후 변경 불가
- `agentName`: 필수, 최대 100자
- `version`: 필수, 최대 30자, `^\d+\.\d+\.\d+$`
- `description`: 필수, 최대 2000자
- `prompt`: 필수, 최대 10000자
- `inputSchema`, `outputSchema`: 필수 JSON Object
- `browserSupport`, `mcpSupport`: 필수 boolean
- `requiredModel`: 선택
- `requiredTools`: 선택, 기본값 빈 배열

등록 ID 중복은 `409 Conflict`, 존재하지 않는 Agent는 `404 Not Found`, Validation 실패나 잘못된 JSON은 `400 Bad Request`입니다.

```json
{
  "status": 404,
  "message": "Agent를 찾을 수 없습니다. id=example",
  "path": "/api/agents/example"
}
```

## 현재 구현된 기능

- 문자열 ID 기반 Agent 등록/목록/상세/수정/삭제
- ID 중복 검사 및 `409 Conflict`
- 이름과 설명 키워드 검색
- Bean Validation 및 공통 오류 JSON
- JSON Object Schema의 TEXT 저장과 Object 응답
- `requiredTools` 컬렉션 저장 및 빈 배열 기본값
- 서버 관리 `anonymous` author와 생성/수정 시간
- 다운로드 가능한 `agent.json`
- `mcpSupport=true` Agent 전용 목록 API
- MySQL 프로필과 H2 test 프로필 분리
- Spring Context 및 HTTP CRUD/실패/다운로드/MCP 목록 통합 테스트

## 현재 구현하지 않은 기능

- 회원가입, 로그인, Google OAuth, Spring Security, Session, JWT
- 실제 Local MCP Server, MCP Sync, MCP Tool 실행과 Claude Desktop 연결 코드
- 실제 Browser Runtime 실행
- LLM 다운로드/선택/실행
- Agent Workflow와 과거 버전 이력
- 결제, 유료 판매, 추천, 평점, 리뷰
- 실시간 채팅, 관리자 페이지, 모바일 앱
- 이미지/파일 입력, 대규모 트래픽 대응, 복잡한 권한 시스템
- ZIP 형태 Agent Package
- Flyway 등 DB 마이그레이션 도구

## 예정 API

인증 방식은 Google OAuth + Session 또는 Google OAuth + JWT 중 아직 결정하지 않았습니다. 다음 API는 계획만 있으며 Controller나 User Entity를 구현하지 않았습니다.

```text
POST /api/auth/logout       로그아웃 후보
GET  /api/auth/me           현재 사용자 후보
GET  /api/users/me          내 정보 조회 후보
GET  /api/users/me/agents   내가 등록한 Agent 조회 후보
```

로그인 URL은 Google OAuth 구현 방식이 확정된 후 결정합니다.

## 개발 일정

```text
1단계 - 각 파트 기본 기능 개발
완료 목표: 미정

2단계 - Agent Package 규격 통일
완료 목표: 미정

3단계 - Frontend ↔ Backend 연결
완료 목표: 미정

4단계 - Browser Runtime ↔ Marketplace 연결
완료 목표: 미정

5단계 - Local MCP ↔ Marketplace 연결
완료 목표: 미정

6단계 - Agent Workflow 통합
완료 목표: 미정

7단계 - 전체 통합 테스트
완료 목표: 미정

8단계 - 버그 수정 및 발표 준비
완료 목표: 미정
```

## 다음 개발 단계

1. 로컬 MySQL에 `agent_marketplace`를 만들고 실제 CRUD 및 한글 검색을 확인합니다.
2. Frontend와 연결해 등록/검색/다운로드 흐름을 검증합니다.
3. 데이터 구조가 안정되면 Flyway 도입을 검토합니다.
4. 인증이 필요해지는 시점에 Google 로그인과 사용자-`author` 연결을 설계합니다.
5. 실행 환경 요구사항이 확정된 뒤 MCP, 브라우저 실행, Workflow를 별도 단계로 추가합니다.
