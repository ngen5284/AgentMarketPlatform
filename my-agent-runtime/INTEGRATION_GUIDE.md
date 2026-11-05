# [AgentMarketPlatform] 3번 파트: 브라우저 실행 런타임 연동 가이드

> **작성자**: 3번 파트 담당자  
> **대상**: 1번(웹 마켓플레이스 프론트엔드), 2번(백엔드 및 에이전트 관리), 4번(로컬 MCP 서버) 조원  
> **위치**: `my-agent-runtime/`

---

## 📌 3번 파트 개요
3번 파트는 **사용자의 웹 브라우저(클라이언트) 환경에서 서버 없이 에이전트와 경량 LLM을 직접 구동하고 순차 워크플로를 처리하는 핵심 엔진**입니다.

* **에이전트 실행**: Pyodide(WASM Python) 및 Web Worker를 통한 안전한 격리 실행
* **오프라인 캐싱**: IndexedDB 및 Cache API를 이용한 패키지 및 가중치 저장
* **온디바이스 LLM**: WebGPU 기반 초경량 모델(SmolLM2, Qwen2.5 등) 로컬 추론
* **워크플로 오케스트레이션**: 에이전트 체이닝 & Human-in-the-Loop(사용자 개입/승인) 파이프라인

---

## 🤝 1번 조원 (웹 마켓플레이스 프론트엔드) 연동 가이드

1번 조원님은 본인이 만든 UI 화면(스토어, 워크플로 에디터 등)에서 아래처럼 3번의 모듈을 `import`하여 함수를 호출하시기만 하면 됩니다.

### 1. 단일 에이전트 실행 방법
```javascript
import { AgentLoader } from "./src/loader/agentLoader.js";

const loader = new AgentLoader();

// 에이전트 실행 (에이전트ID, 작업지시문)
const response = await loader.executeAgent("text_analyzer", "분석할 텍스트입니다.");
console.log(response.output);      // 에이전트 실행 결과 문자열
console.log(response.durationMs);  // 소요 시간(ms)
```

### 2. 순차 워크플로 & Human-in-the-Loop 파이프라인 구동
```javascript
import { WorkflowEngine } from "./src/workflow/workflowEngine.js";

const workflow = new WorkflowEngine(loader, llmEngine);

// 사용자 승인이 필요한 단계는 requireApproval: true 부여
workflow.onApprovalRequired = ({ stepIndex, step, output, resolve, reject }) => {
    // 1번 조원님의 예쁜 모달 UI를 띄워 사용자에게 output을 보여주고 승인/수정 받기
    const userEditedData = prompt("생성된 데이터를 검토 후 수정하세요:", output);
    if (userEditedData !== null) {
        resolve(userEditedData); // 다음 단계로 전달
    } else {
        reject("사용자 거절");
    }
};

const pipeline = [
    { type: "agent", agentId: "text_analyzer", label: "1단계: 텍스트 분석" },
    { type: "llm", prompt: "분석 결과를 요약해줘: {{prev}}", label: "2단계: LLM 요약", requireApproval: true },
    { type: "agent", agentId: "demo_agent", label: "3단계: 최종 보고" }
];

const results = await workflow.run(pipeline, "시작 텍스트 데이터");
```

---

## 📦 2번 조원 (백엔드 및 에이전트 관리) 연동 규격

2번 조원님이 에이전트 마켓플레이스 서버에서 에이전트를 배포/다운로드할 때 내려주시는 패키지 규격입니다.

### 1. 에이전트 패키지 구성 (ZIP 파일 또는 JSON)
ZIP 파일 내부에 아래 파일들이 들어있으면 브라우저 런타임이 드래그&드롭 또는 API 다운로드 시 자동 압축 해제 및 설치합니다:
```
my_agent.zip
├── manifest.json   (필수)
├── agent.py        (필수: 실행 진입점 코드)
└── integrity.json  (선택: SHA-256 무결성 검증 해시)
```

### 2. `manifest.json` 표준 형식
```json
{
  "id": "calculator",
  "name": "수학 계산기 에이전트",
  "description": "사칙연산 및 수학 표현식을 계산합니다.",
  "entrypoint": "agent.py",
  "version": "1.0.0"
}
```

### 3. `agent.py` 진입점 함수 표준
```python
def run(task: str) -> str:
    # 전달받은 task 문자열을 처리하여 결과 문자열 반환
    return f"작업 완료: {task}"
```

---

## 🔌 4번 조원 (로컬 MCP 서버 및 커넥터)과의 호환성
* 3번 브라우저 런타임의 에이전트 패키지 규격(`manifest.json`, `agent.py`, `integrity.json`)은 **4번 조원님의 로컬 MCP 서버 규격과 100% 동일하게 호환**됩니다.
* 즉, 사용자가 마켓에서 내려받은 동일한 에이전트 패키지를 로컬 MCP 서버(Claude Desktop용)에서도 돌릴 수 있고, 브라우저 온디바이스에서도 무수정으로 그대로 실행할 수 있습니다.

---

## 💻 실행 및 테스트 환경
```powershell
cd my-agent-runtime
npm.cmd run dev
```
브라우저(`http://localhost:5173`)에서 모든 기능이 즉시 테스트 가능하도록 준비되어 있습니다. 연동 시 문의사항이 있으시면 언제든 편하게 말씀해 주세요!

