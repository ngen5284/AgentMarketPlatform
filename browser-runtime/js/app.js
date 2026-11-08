import { AgentRunner } from "./agent-runner.js";
import { StorageManager } from "./storage-manager.js";
import { LLMEngine } from "./llm-engine.js";
import { WorkflowEngine } from "./workflow-engine.js";

// DOM 요소 참조
const webgpuBadge = document.getElementById("webgpuBadge");
const agentCountBadge = document.getElementById("agentCountBadge");
const selectAgent = document.getElementById("selectAgent");
const agentTaskInput = document.getElementById("agentTaskInput");
const btnRunAgent = document.getElementById("btnRunAgent");
const agentResultBox = document.getElementById("agentResultBox");
const btnLoadTextAnalyzer = document.getElementById("btnLoadTextAnalyzer");
const btnLoadDemoAgent = document.getElementById("btnLoadDemoAgent");
const btnClearCache = document.getElementById("btnClearCache");

const selectModel = document.getElementById("selectModel");
const btnLoadModel = document.getElementById("btnLoadModel");
const llmStatusBadge = document.getElementById("llmStatusBadge");
const modelProgressFill = document.getElementById("modelProgressFill");
const modelProgressText = document.getElementById("modelProgressText");
const llmPromptInput = document.getElementById("llmPromptInput");
const btnRunLLM = document.getElementById("btnRunLLM");
const llmResultBox = document.getElementById("llmResultBox");

const btnRunWorkflow = document.getElementById("btnRunWorkflow");
const workflowInput = document.getElementById("workflowInput");
const systemLog = document.getElementById("systemLog");

// 인스턴스 생성
const runner = new AgentRunner("js/agent-worker.js");
const storage = new StorageManager();
const llm = new LLMEngine();
const workflow = new WorkflowEngine(runner, llm);

function log(msg, type = "info") {
    const time = new Date().toLocaleTimeString();
    const line = `[${time}] ${msg}\n`;
    systemLog.textContent += line;
    systemLog.scrollTop = systemLog.scrollHeight;
    console.log(line);
}

// 내장 샘플 에이전트 데이터
const SAMPLE_AGENTS = {
    text_analyzer: {
        id: "text_analyzer",
        manifest: {
            id: "text_analyzer",
            name: "텍스트 분석 에이전트",
            description: "입력된 텍스트의 글자 수와 단어 수를 분석합니다.",
            entrypoint: "agent.py"
        },
        code: `def run(task: str) -> str:
    char_count = len(task)
    word_count = len(task.split())
    return (
        "텍스트 분석 완료!\\n"
        f"입력 내용: {task}\\n"
        f"글자 수: {char_count}\\n"
        f"단어 수: {word_count}"
    )
`
    },
    demo_agent: {
        id: "demo_agent",
        manifest: {
            id: "demo_agent",
            name: "테스트 에이전트",
            description: "로컬 패키지 로딩 검증용 에이전트",
            entrypoint: "agent.py"
        },
        code: `def run(task: str) -> str:
    return (
        "로컬 에이전트 실행 성공!\\n"
        f"에이전트: 테스트 에이전트\\n"
        f"요청 내용: {task}"
    )
`
    }
};

// UI 에이전트 셀렉트박스 갱신
async function refreshAgentSelect() {
    const savedAgents = await storage.getAllAgents();
    selectAgent.innerHTML = "";

    if (savedAgents.length === 0) {
        selectAgent.innerHTML = '<option value="">(설치된 에이전트 없음)</option>';
        agentCountBadge.textContent = "0개 로드됨";
        return;
    }

    savedAgents.forEach(agent => {
        const opt = document.createElement("option");
        opt.value = agent.id;
        opt.textContent = `${agent.manifest.name} (${agent.id})`;
        selectAgent.appendChild(opt);
    });

    agentCountBadge.textContent = `${savedAgents.length}개 로드됨`;
}

// 에이전트 설치 & 러너에 로드
async function installAndLoadAgent(agentData) {
    try {
        log(`에이전트 [${agentData.id}] 저장소(IndexedDB) 저장 중...`);
        await storage.saveAgent(agentData);

        log(`에이전트 [${agentData.id}] Pyodide Worker 런타임에 마운트 중...`);
        await runner.loadAgent(agentData.manifest, agentData.code);

        await refreshAgentSelect();
        selectAgent.value = agentData.id;
        log(`✅ 에이전트 [${agentData.manifest.name}] 준비 완료`);
    } catch (err) {
        log(`❌ 에이전트 설치 실패: ${err.message}`, "error");
    }
}

// 초기화
async function initApp() {
    log("🚀 브라우저 실행 환경(Browser Runtime) 초기화 시작");

    // 1. WebGPU 지원 검사
    const hasWebGPU = LLMEngine.checkWebGPUSupport();
    if (hasWebGPU) {
        webgpuBadge.textContent = "WebGPU 활성화됨 (하드웨어 가속)";
        webgpuBadge.className = "badge success";
        log("WebGPU 하드웨어 가속 지원 감지됨");
    } else {
        webgpuBadge.textContent = "WebGPU 미지원 (호환 모드로 동작)";
        webgpuBadge.className = "badge warning";
        log("WebGPU 미지원 환경: 브라우저 LLM 호환 모드 적용");
    }

    // 2. 모델 옵션 채우기
    llm.getAvailableModels().forEach(m => {
        const opt = document.createElement("option");
        opt.value = m.id;
        opt.textContent = `${m.name} (${m.size}) - ${m.description}`;
        selectModel.appendChild(opt);
    });

    // 3. Worker 및 Storage 초기화
    runner.onStatusChange = (status) => log(`[Worker 상태] ${status}`);
    runner.onLog = (lvl, txt) => log(`[Pyodide] ${txt}`);

    await storage.init();
    await refreshAgentSelect();

    // 저장소에 에이전트가 있다면 런타임에 자동 마운트
    const saved = await storage.getAllAgents();
    for (const item of saved) {
        await runner.loadAgent(item.manifest, item.code);
    }

    log("✨ 초기화 완료. 에이전트 실행 또는 워크플로를 시작하세요.");
}

// 이벤트 리스너 바인딩
btnLoadTextAnalyzer.addEventListener("click", () => installAndLoadAgent(SAMPLE_AGENTS.text_analyzer));
btnLoadDemoAgent.addEventListener("click", () => installAndLoadAgent(SAMPLE_AGENTS.demo_agent));

btnClearCache.addEventListener("click", async () => {
    if (confirm("브라우저에 저장된 에이전트와 캐시를 모두 비우시겠습니까?")) {
        await storage.clearAll();
        await refreshAgentSelect();
        log("🧹 저장소 캐시 삭제 완료");
    }
});

btnRunAgent.addEventListener("click", async () => {
    const agentId = selectAgent.value;
    const task = agentTaskInput.value.trim();

    if (!agentId) {
        alert("실행할 에이전트를 먼저 선택하거나 설치해주세요.");
        return;
    }

    try {
        btnRunAgent.disabled = true;
        agentResultBox.textContent = "에이전트 실행 중...";
        log(`에이전트 [${agentId}] 실행 요청...`);

        const res = await runner.runAgent(agentId, task);
        agentResultBox.textContent = res.result;
        log(`✅ 실행 성공 (${res.durationMs}ms)`);
    } catch (err) {
        agentResultBox.textContent = `에러: ${err.message}`;
        log(`❌ 실행 에러: ${err.message}`, "error");
    } finally {
        btnRunAgent.disabled = false;
    }
});

// LLM 로드
btnLoadModel.addEventListener("click", async () => {
    const modelId = selectModel.value;
    btnLoadModel.disabled = true;
    llmStatusBadge.textContent = "로딩 중...";
    llmStatusBadge.className = "badge warning";

    llm.onProgress = (report) => {
        const pct = Math.round((report.progress || 0) * 100);
        modelProgressFill.style.width = `${pct}%`;
        modelProgressText.textContent = `[${pct}%] ${report.text}`;
    };

    try {
        log(`경량 LLM [${modelId}] 로딩 시작...`);
        await llm.loadModel(modelId);
        llmStatusBadge.textContent = llm.isFallback ? "호환 모드 준비됨" : "WebGPU 준비됨";
        llmStatusBadge.className = "badge success";
        log(`✅ LLM 로딩 완료!`);
    } catch (err) {
        llmStatusBadge.textContent = "로딩 실패";
        log(`❌ LLM 로딩 실패: ${err.message}`, "error");
    } finally {
        btnLoadModel.disabled = false;
    }
});

// LLM 단독 실행
btnRunLLM.addEventListener("click", async () => {
    const prompt = llmPromptInput.value.trim();
    if (!prompt) return;

    btnRunLLM.disabled = true;
    llmResultBox.textContent = "";
    log("LLM 추론 요청 전송...");

    try {
        await llm.generate(prompt, (token) => {
            llmResultBox.textContent += token;
            llmResultBox.scrollTop = llmResultBox.scrollHeight;
        });
        log("✅ LLM 추론 완료");
    } catch (err) {
        llmResultBox.textContent = `오류: ${err.message}`;
        log(`❌ LLM 에러: ${err.message}`, "error");
    } finally {
        btnRunLLM.disabled = false;
    }
});

// 순차 워크플로 파이프라인 실행
btnRunWorkflow.addEventListener("click", async () => {
    const input = workflowInput.value.trim();
    if (!input) {
        alert("워크플로에 전달할 입력 데이터를 입력해주세요.");
        return;
    }

    // 워크플로에 필요한 기본 에이전트들이 설치되어 있는지 확인 및 자동 설치
    await installAndLoadAgent(SAMPLE_AGENTS.text_analyzer);
    await installAndLoadAgent(SAMPLE_AGENTS.demo_agent);

    // 파이프라인 단계 정의
    const steps = [
        {
            type: "agent",
            agentId: "text_analyzer",
            label: "1단계: 텍스트 분석 에이전트"
        },
        {
            type: "llm",
            prompt: "아래 텍스트 분석 결과를 바탕으로 주요 요약과 결론을 간결하게 작성해줘:\n\n{{prev}}",
            label: "2단계: 온디바이스 LLM 요약"
        },
        {
            type: "agent",
            agentId: "demo_agent",
            label: "3단계: 최종 보고서 확정"
        }
    ];

    // UI 상태 리셋
    const stepCards = [
        { card: document.getElementById("stepCard1"), status: document.getElementById("step1Status"), out: document.getElementById("step1Output") },
        { card: document.getElementById("stepCard2"), status: document.getElementById("step2Status"), out: document.getElementById("step2Output") },
        { card: document.getElementById("stepCard3"), status: document.getElementById("step3Status"), out: document.getElementById("step3Output") }
    ];

    stepCards.forEach(s => {
        s.card.className = "step-card";
        s.status.textContent = "대기";
        s.status.className = "badge";
        s.out.style.display = "none";
        s.out.textContent = "";
    });

    workflow.onStepStart = (index, step) => {
        log(`▶ [${step.label}] 시작`);
        stepCards[index].card.className = "step-card active";
        stepCards[index].status.textContent = "실행 중...";
        stepCards[index].status.className = "badge warning";
    };

    workflow.onStepComplete = (index, step, res) => {
        log(`✅ [${step.label}] 완료 (${res.durationMs}ms)`);
        stepCards[index].card.className = "step-card completed";
        stepCards[index].status.textContent = `완료 (${res.durationMs}ms)`;
        stepCards[index].status.className = "badge success";
        stepCards[index].out.style.display = "block";
        stepCards[index].out.textContent = res.output;
    };

    workflow.onStepError = (index, step, err) => {
        log(`❌ [${step.label}] 실패: ${err.error}`, "error");
        stepCards[index].card.className = "step-card";
        stepCards[index].status.textContent = "에러";
        stepCards[index].status.className = "badge";
        stepCards[index].out.style.display = "block";
        stepCards[index].out.textContent = `실패: ${err.error}`;
    };

    btnRunWorkflow.disabled = true;
    try {
        log("🏁 순차 워크플로 파이프라인 일괄 실행 시작...");
        await workflow.executeWorkflow(steps, input);
        log("🎉 모든 순차 워크플로 단계가 성공적으로 완료되었습니다!");
    } catch (err) {
        log(`🚨 워크플로 중단: ${err.message}`, "error");
    } finally {
        btnRunWorkflow.disabled = false;
    }
});

initApp();

