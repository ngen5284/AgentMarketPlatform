/**
 * main.js - My Agent Runtime 진입점
 */

import { AgentLoader } from "./loader/agentLoader.js";
import { IndexedDbCache } from "./storage/indexedDbCache.js";
import { WebGpuLlmEngine } from "./llm/webGpuLlmEngine.js";
import { WorkflowEngine } from "./workflow/workflowEngine.js";

// DOM 요소 바인딩
const gpuStatusBadge = document.getElementById("gpuStatusBadge");
const storageUsageBadge = document.getElementById("storageUsageBadge");
const selectAgent = document.getElementById("selectAgent");
const agentInput = document.getElementById("agentInput");
const btnRunSingleAgent = document.getElementById("btnRunSingleAgent");
const btnClearStorage = document.getElementById("btnClearStorage");
const agentOutputBox = document.getElementById("agentOutputBox");
const btnInstallTextAnalyzer = document.getElementById("btnInstallTextAnalyzer");
const btnInstallDemoAgent = document.getElementById("btnInstallDemoAgent");

// 드래그 & 드롭 요소
const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const btnSelectFiles = document.getElementById("btnSelectFiles");

const selectModel = document.getElementById("selectModel");
const btnLoadModel = document.getElementById("btnLoadModel");
const llmBadge = document.getElementById("llmBadge");
const llmProgressFill = document.getElementById("llmProgressFill");
const llmProgressText = document.getElementById("llmProgressText");
const llmPrompt = document.getElementById("llmPrompt");
const btnRunSingleLLM = document.getElementById("btnRunSingleLLM");
const llmOutputBox = document.getElementById("llmOutputBox");

const btnStartWorkflow = document.getElementById("btnStartWorkflow");
const btnAbortWorkflow = document.getElementById("btnAbortWorkflow");
const workflowInput = document.getElementById("workflowInput");
const logConsole = document.getElementById("logConsole");

// HITL 모달 요소
const hitlModal = document.getElementById("hitlModal");
const hitlDataInput = document.getElementById("hitlDataInput");
const btnHitlApprove = document.getElementById("btnHitlApprove");
const btnHitlReject = document.getElementById("btnHitlReject");

// 모듈 인스턴스 초기화
const loader = new AgentLoader();
const cache = new IndexedDbCache();
const llm = new WebGpuLlmEngine();
const workflow = new WorkflowEngine(loader, llm);

let activeHitlContext = null;

function log(msg, type = "info") {
    const time = new Date().toLocaleTimeString();
    const line = `[${time}] ${msg}\n`;
    logConsole.textContent += line;
    logConsole.scrollTop = logConsole.scrollHeight;
    console.log(line);
}

// 내장 샘플 에이전트 소스
const BUILTIN_PACKAGES = {
    text_analyzer: {
        id: "text_analyzer",
        manifest: {
            id: "text_analyzer",
            name: "텍스트 분석 에이전트",
            description: "입력된 텍스트의 글자 수 및 단어 수를 세부 분석합니다.",
            entrypoint: "agent.py",
            version: "1.0.0"
        },
        code: `def run(task: str) -> str:
    char_count = len(task)
    word_count = len(task.split())
    line_count = len(task.splitlines())
    return (
        "📊 [텍스트 분석 결과]\\n"
        f"입력: {task}\\n"
        f"• 총 글자 수: {char_count}자\\n"
        f"• 단어 수: {word_count}단어\\n"
        f"• 줄 수: {line_count}줄"
    )
`
    },
    demo_agent: {
        id: "demo_agent",
        manifest: {
            id: "demo_agent",
            name: "보고서 생성 에이전트",
            description: "이전 단계의 결과를 취합하여 최종 보고서를 확정합니다.",
            entrypoint: "agent.py",
            version: "1.0.0"
        },
        code: `def run(task: str) -> str:
    return (
        "📝 [최종 워크플로 완료 보고서]\\n"
        "상태: 성공적으로 승인 및 처리됨\\n"
        "취합 내용:\\n"
        f"{task}"
    )
`
    }
};

// UI 갱신 함수들
async function updateStorageStats() {
    const est = await cache.estimateStorage();
    storageUsageBadge.textContent = `스토리지: ${est.usageMB} MB (${est.percentage}%)`;
}

async function refreshAgentSelect() {
    const agents = await cache.getAllAgents();
    selectAgent.innerHTML = "";

    if (agents.length === 0) {
        selectAgent.innerHTML = '<option value="">(설치된 에이전트 없음)</option>';
        return;
    }

    agents.forEach(a => {
        const opt = document.createElement("option");
        opt.value = a.id;
        opt.textContent = `${a.manifest.name} (${a.id})`;
        selectAgent.appendChild(opt);
    });

    await updateStorageStats();
}

async function installPackage(pkg) {
    try {
        log(`에이전트 [${pkg.id}] IndexedDB 캐싱 중...`);
        await cache.saveAgent(pkg);

        log(`에이전트 [${pkg.id}] Web Worker 격리 환경 로딩 중...`);
        await loader.loadPackage(pkg);

        await refreshAgentSelect();
        selectAgent.value = pkg.id;
        log(`✅ 에이전트 [${pkg.manifest.name}] 준비 완료`);
    } catch (err) {
        log(`❌ 에이전트 설치 실패: ${err.message}`, "error");
        throw err;
    }
}

// 드래그 앤 드롭 파일 처리
async function handleUploadedFiles(files) {
    try {
        log(`📂 파일 수신됨: ${files.length}개 파일 파싱 시작...`);
        let pkg;
        if (files.length === 1 && files[0].name.endsWith(".zip")) {
            log(`📦 ZIP 아카이브 압축 해제 중: ${files[0].name}`);
            pkg = await loader.parseZipPackage(files[0]);
        } else {
            pkg = await loader.parseFiles(files);
        }

        await installPackage(pkg);
        log(`🎉 새 에이전트 [${pkg.manifest.name}] 설치가 완료되었습니다!`);
    } catch (err) {
        log(`❌ 에이전트 파일 설치 오류: ${err.message}`, "error");
        alert(`에이전트 설치 오류: ${err.message}`);
    }
}

// 초기화
async function init() {
    log("🚀 [My Agent Runtime] 초기화 시작...");

    // 1. WebGPU 감지
    const gpuCheck = await WebGpuLlmEngine.detectWebGpu();
    if (gpuCheck.supported) {
        gpuStatusBadge.textContent = `WebGPU 가속: ${gpuCheck.vendor}`;
        gpuStatusBadge.className = "badge success";
        log(`WebGPU 디바이스 감지 성공: ${gpuCheck.description}`);
    } else {
        gpuStatusBadge.textContent = "WebGPU 미지원 (호환 모드)";
        gpuStatusBadge.className = "badge warning";
        log(`WebGPU 미지원: ${gpuCheck.reason}`);
    }

    // 2. 모델 카탈로그 바인딩
    WebGpuLlmEngine.getModelCatalog().forEach(m => {
        const opt = document.createElement("option");
        opt.value = m.id;
        opt.textContent = `${m.name} (${m.size}) - ${m.description}`;
        selectModel.appendChild(opt);
    });

    // 3. Worker 및 Storage 로깅 콜백 등록
    loader.onStatus = (msg) => log(`[Worker 상태] ${msg}`);
    loader.onLog = (lvl, msg) => log(`[Pyodide] ${msg}`);

    await cache.init();
    await refreshAgentSelect();

    // 저장소에 기존 에이전트가 있으면 자동 복원
    const cached = await cache.getAllAgents();
    for (const item of cached) {
        await loader.loadPackage(item);
    }

    log("✨ 런타임 준비 완료.");
}

// 드래그 앤 드롭 이벤트 등록
btnSelectFiles.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", async (e) => {
    if (e.target.files && e.target.files.length > 0) {
        await handleUploadedFiles(e.target.files);
        fileInput.value = "";
    }
});

dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
});

dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragover");
});

dropZone.addEventListener("drop", async (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        await handleUploadedFiles(e.dataTransfer.files);
    }
});

// 이벤트 리스너 바인딩
btnInstallTextAnalyzer.addEventListener("click", () => installPackage(BUILTIN_PACKAGES.text_analyzer));
btnInstallDemoAgent.addEventListener("click", () => installPackage(BUILTIN_PACKAGES.demo_agent));

btnClearStorage.addEventListener("click", async () => {
    if (confirm("IndexedDB에 저장된 모든 에이전트와 캐시를 삭제하시겠습니까?")) {
        await cache.clearAll();
        await refreshAgentSelect();
        log("🧹 저장소 캐시 초기화 완료");
    }
});

btnRunSingleAgent.addEventListener("click", async () => {
    const id = selectAgent.value;
    const task = agentInput.value.trim();

    if (!id) {
        alert("실행할 에이전트를 먼저 선택하거나 설치해주세요.");
        return;
    }

    btnRunSingleAgent.disabled = true;
    agentOutputBox.textContent = "실행 중...";
    try {
        log(`에이전트 [${id}] 단독 실행 요청...`);
        const res = await loader.executeAgent(id, task);
        agentOutputBox.textContent = res.output;
        log(`✅ 에이전트 실행 성공 (${res.durationMs}ms)`);
    } catch (err) {
        agentOutputBox.textContent = `오류: ${err.message}`;
        log(`❌ 에이전트 실행 오류: ${err.message}`, "error");
    } finally {
        btnRunSingleAgent.disabled = false;
    }
});

btnLoadModel.addEventListener("click", async () => {
    const modelId = selectModel.value;
    btnLoadModel.disabled = true;
    llmBadge.textContent = "로딩 중...";
    llmBadge.className = "badge warning";

    llm.onProgress = (report) => {
        const pct = Math.round((report.progress || 0) * 100);
        llmProgressFill.style.width = `${pct}%`;
        llmProgressText.textContent = `[${pct}%] ${report.text}`;
    };

    try {
        log(`경량 LLM [${modelId}] 다운로드/초기화 중...`);
        await llm.loadModel(modelId);
        llmBadge.textContent = llm.isFallbackMode ? "호환 모드" : "WebGPU 준비";
        llmBadge.className = "badge success";
        log("✅ LLM 엔진 준비 완료");
    } catch (err) {
        llmBadge.textContent = "실패";
        log(`❌ LLM 초기화 실패: ${err.message}`, "error");
    } finally {
        btnLoadModel.disabled = false;
    }
});

btnRunSingleLLM.addEventListener("click", async () => {
    const prompt = llmPrompt.value.trim();
    if (!prompt) return;

    btnRunSingleLLM.disabled = true;
    llmOutputBox.textContent = "";

    try {
        log("LLM 스트리밍 추론 시작...");
        await llm.generate(prompt, (token) => {
            llmOutputBox.textContent += token;
            llmOutputBox.scrollTop = llmOutputBox.scrollHeight;
        });
        log("✅ LLM 추론 완료");
    } catch (err) {
        llmOutputBox.textContent = `오류: ${err.message}`;
    } finally {
        btnRunSingleLLM.disabled = false;
    }
});

// 워크플로 UI 핸들러
const pipeSteps = [
    { card: document.getElementById("pipeStep1"), out: document.getElementById("pipeStep1Output") },
    { card: document.getElementById("pipeStep2"), out: document.getElementById("pipeStep2Output") },
    { card: document.getElementById("pipeStep3"), out: document.getElementById("pipeStep3Output") }
];

workflow.onStepStart = (index, step) => {
    log(`▶ [${step.label}] 시작`);
    pipeSteps[index].card.className = "pipe-card active";
};

workflow.onStepComplete = (index, step, res) => {
    log(`✅ [${step.label}] 완료 (${res.durationMs}ms)`);
    pipeSteps[index].card.className = "pipe-card completed";
    pipeSteps[index].out.style.display = "block";
    pipeSteps[index].out.textContent = res.output;
};

workflow.onStepError = (index, step, err) => {
    log(`❌ [${step.label}] 실패: ${err.error}`, "error");
    pipeSteps[index].card.className = "pipe-card";
    pipeSteps[index].out.style.display = "block";
    pipeSteps[index].out.textContent = `실패: ${err.error}`;
};

// Human-in-the-Loop 승인 모달 핸들링
workflow.onApprovalRequired = ({ stepIndex, step, output, resolve, reject }) => {
    log(`⚠️ [Human-in-the-Loop] ${step.label} 결과에 대한 사용자 승인 대기 중...`);
    pipeSteps[stepIndex].card.className = "pipe-card waiting-approval";

    hitlDataInput.value = output;
    hitlModal.className = "modal-overlay open";

    activeHitlContext = { resolve, reject, stepIndex };
};

btnHitlApprove.addEventListener("click", () => {
    if (activeHitlContext) {
        const approvedData = hitlDataInput.value;
        hitlModal.className = "modal-overlay";
        log("👍 사용자가 중간 데이터를 승인/수정하고 다음 단계로 전달했습니다.");
        activeHitlContext.resolve(approvedData);
        activeHitlContext = null;
    }
});

btnHitlReject.addEventListener("click", () => {
    if (activeHitlContext) {
        hitlModal.className = "modal-overlay";
        log("🛑 사용자가 워크플로 진행을 거절했습니다.");
        activeHitlContext.reject("사용자 거절로 워크플로 중단됨");
        activeHitlContext = null;
    }
});

btnAbortWorkflow.addEventListener("click", () => {
    workflow.abort();
    log("🛑 사용자 워크플로 중단 요청");
});

btnStartWorkflow.addEventListener("click", async () => {
    const input = workflowInput.value.trim();
    if (!input) {
        alert("워크플로에 전달할 원본 텍스트를 입력해주세요.");
        return;
    }

    // 필수 에이전트 확인 및 자동 설치
    await installPackage(BUILTIN_PACKAGES.text_analyzer);
    await installPackage(BUILTIN_PACKAGES.demo_agent);

    // 파이프라인 정의 (2단계에 requireApproval: true 설정!)
    const pipeline = [
        {
            type: "agent",
            agentId: "text_analyzer",
            label: "Step 1: 텍스트 분석"
        },
        {
            type: "llm",
            prompt: "아래 텍스트 분석 데이터를 핵심 위주로 요약하고 조언을 작성해줘:\n\n{{prev}}",
            label: "Step 2: LLM 요약",
            requireApproval: true // Human-in-the-Loop 활성화!
        },
        {
            type: "agent",
            agentId: "demo_agent",
            label: "Step 3: 최종 보고서 확정"
        }
    ];

    // UI 리셋
    pipeSteps.forEach(p => {
        p.card.className = "pipe-card";
        p.out.style.display = "none";
        p.out.textContent = "";
    });

    btnStartWorkflow.style.display = "none";
    btnAbortWorkflow.style.display = "inline-flex";

    try {
        log("🏁 Human-in-the-Loop 워크플로 파이프라인 시작...");
        const history = await workflow.run(pipeline, input);
        await cache.saveWorkflowHistory({ history, input });
        log("🎉 모든 파이프라인 단계가 성공적으로 완료되었습니다!");
    } catch (err) {
        log(`🚨 워크플로 중단: ${err.message}`, "error");
    } finally {
        btnStartWorkflow.style.display = "inline-flex";
        btnAbortWorkflow.style.display = "none";
    }
});

init();
