/**
 * Agent Worker (Web Worker)
 * - 브라우저 백그라운드 스레드에서 WASM 기반 Pyodide를 초기화하여 Python 에이전트를 안전하게 실행합니다.
 * - 메인 UI 스레드가 멈추지(Freeze) 않도록 분리된 환경을 제공합니다.
 */

// Pyodide CDN 주소
const PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js";

let pyodide = null;
let isInitializing = false;
let installedAgents = new Map(); // agentId -> { manifest, entrypointCode }

async function getPyodide() {
    if (pyodide) return pyodide;
    if (isInitializing) {
        while (isInitializing) {
            await new Promise(r => setTimeout(r, 100));
        }
        return pyodide;
    }

    isInitializing = true;
    try {
        postMessage({ type: "STATUS", message: "Pyodide WASM Python 런타임 다운로드 및 초기화 중..." });
        importScripts(PYODIDE_CDN);
        pyodide = await loadPyodide({
            stdout: (text) => postMessage({ type: "LOG", level: "info", text }),
            stderr: (text) => postMessage({ type: "LOG", level: "warn", text })
        });
        postMessage({ type: "STATUS", message: "Pyodide 초기화 완료" });
        return pyodide;
    } finally {
        isInitializing = false;
    }
}

self.onmessage = async (event) => {
    const { id, type, payload } = event.data;

    try {
        switch (type) {
            case "INIT": {
                await getPyodide();
                postMessage({ id, type: "INIT_SUCCESS" });
                break;
            }

            case "LOAD_AGENT": {
                const { manifest, code } = payload;
                if (!manifest || !manifest.id || !code) {
                    throw new Error("올바른 manifest 및 코드가 필요합니다.");
                }

                const runtime = await getPyodide();

                // 에이전트 전용 가상 디렉토리 생성 및 코드 마운트
                const agentDir = `/agents/${manifest.id}`;
                runtime.FS.mkdirTree(agentDir);
                const filePath = `${agentDir}/${manifest.entrypoint || "agent.py"}`;
                runtime.FS.writeFile(filePath, code, { encoding: "utf8" });

                installedAgents.set(manifest.id, {
                    manifest,
                    filePath,
                    language: manifest.entrypoint?.endsWith(".js") ? "js" : "python"
                });

                postMessage({
                    id,
                    type: "LOAD_SUCCESS",
                    agentId: manifest.id,
                    name: manifest.name
                });
                break;
            }

            case "RUN_AGENT": {
                const { agentId, task } = payload;
                const agent = installedAgents.get(agentId);
                if (!agent) {
                    throw new Error(`에이전트를 찾을 수 없습니다: ${agentId}`);
                }

                let result = "";
                const startTime = performance.now();

                if (agent.language === "python") {
                    const runtime = await getPyodide();
                    
                    // Python 모듈 로드 및 run(task) 함수 실행
                    const pyCode = `
import sys
import importlib.util
from pathlib import Path

agent_file = Path('${agent.filePath}')
agent_dir = str(agent_file.parent)
if agent_dir not in sys.path:
    sys.path.insert(0, agent_dir)

spec = importlib.util.spec_from_file_location("agent_mod_${agentId}", str(agent_file))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

if hasattr(mod, "run"):
    __agent_output__ = str(mod.run(${JSON.stringify(task)}))
else:
    __agent_output__ = "오류: agent에 run(task) 함수가 정의되어 있지 않습니다."
`;
                    await runtime.runPythonAsync(pyCode);
                    result = runtime.globals.get("__agent_output__");
                } else {
                    // JavaScript 에이전트 지원
                    const fn = new Function("task", agent.entrypointCode);
                    result = await fn(task);
                }

                const duration = Math.round(performance.now() - startTime);

                postMessage({
                    id,
                    type: "RUN_SUCCESS",
                    agentId,
                    task,
                    result,
                    durationMs: duration
                });
                break;
            }

            case "LIST_AGENTS": {
                const list = Array.from(installedAgents.values()).map(a => a.manifest);
                postMessage({ id, type: "LIST_SUCCESS", agents: list });
                break;
            }

            default:
                throw new Error(`알 수 없는 메시지 타입: ${type}`);
        }
    } catch (err) {
        postMessage({
            id,
            type: "ERROR",
            error: err.message || String(err)
        });
    }
};

