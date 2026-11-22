# AgentHub 마켓플레이스 (웹 화면)

캡스톤 프로젝트의 에이전트 마켓플레이스 프론트엔드입니다. 빌드 도구 없이 HTML, CSS, JavaScript만으로 동작합니다.

## 폴더 구조

```
agenthub/
├─ index.html   화면 골격 (상단 내비, 본문 영역)
├─ styles.css   전체 스타일 (라이트/다크 테마, 반응형)
├─ app.js       화면 로직 (목록·상세·버전 관리·등록·다운로드)
└─ README.md
```

## Visual Studio Code에서 실행하기

1. VS Code에서 `파일 > 폴더 열기`로 `agenthub` 폴더를 엽니다.
2. 확장 프로그램 **Live Server** (제작자: Ritwick Dey)를 설치합니다.
3. `index.html`을 열고 우측 하단의 **Go Live**를 누르거나, 파일을 우클릭해 `Open with Live Server`를 선택합니다.
4. 브라우저에서 `http://127.0.0.1:5500` 이 열립니다. 코드를 저장하면 화면이 자동으로 새로고침됩니다.

Live Server 없이도 `index.html`을 브라우저로 직접 열면 실행됩니다. 폰트는 인터넷 연결이 있어야 적용됩니다.

## app.js 구성

| 구역 | 내용 | 담당 역할 |
|------|------|-----------|
| 0. 데이터 | 샘플 에이전트 목록과 내 다운로드 상태 | 백엔드 연동 시 교체 |
| 3. viewBrowse | 에이전트 검색·목록 화면 | 에이전트 검색 |
| 4. viewDetail | 에이전트 상세 정보 (개요, 설치 방법) | 상세 정보 화면 |
| 5. panelVersions, viewDownloads | 버전 기록, 새 버전 배포, 내 다운로드 | 다운로드·버전 관리 |
| 6. viewRegister | 에이전트 등록 폼과 검증 | 에이전트 등록 |
| 7. 이벤트·라우터 | 해시 라우팅(`#browse`, `#register`, `#downloads`, `#agent-<id>`) | 사용자 인터페이스 |

## 백엔드 연동 시 바꿀 곳

- `agents` 배열 → `fetch('/api/agents')` 결과로 교체
- `download()` 함수 → 실제 다운로드 주소 호출 (`/api/agents/:id/versions/:version/download`)
- `submitRegister()` → 등록 API(`POST /api/agents`)로 패키지 파일과 manifest 전송
- 새 버전 배포 폼 제출 처리 → `POST /api/agents/:id/versions`
