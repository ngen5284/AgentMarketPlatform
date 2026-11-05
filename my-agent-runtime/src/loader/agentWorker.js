/**
 * [1] agentWorker.js (Web Worker - ES Module)
 * - 브라우저 백그라운드 스레드에서 WASM 기반 Pyodide를 구동하여 에이전트 코드를 안전하게 실행합니다.
 */

const PYODIDE_MJS = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.mjs";
const PYODIDE_INDEX_URL = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";

let pyodide = null;
let isInitializing = false;
const loadedAgents = new Map();

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
        postMessage({ type: "STATUS", message: "Pyodide WASM 런타임 다운로드 및 초기화 중..." });
        
        // ES Module 환경에서 동적 import로 loadPyodide 불러오기
        const { loadPyodide } = await import(PYODIDE_MJS);
        pyodide = await loadPyodide({
            indexURL: PYODIDE_INDEX_URL,
            stdout: (text) => postMessage({ type: "LOG", level: "info", text }),
            stderr: (text) => postMessage({ type: "LOG", level: "warn", text })
        });
        postMessage({ type: "STATUS", message: "Pyodide WASM 런타임 준비 완료" });
        return pyodide;
    } catch (err) {
        postMessage({ type: "STATUS", message: `Pyodide 초기화 오류: ${err.message}` });
        throw err;
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
                const runtime = await getPyodide();

                const agentDir = `/agents/${manifest.id}`;
                runtime.FS.mkdirTree(agentDir);
                const entryFile = manifest.entrypoint || "agent.py";
                const filePath = `${agentDir}/${entryFile}`;
                runtime.FS.writeFile(filePath, code, { encoding: "utf8" });

                loadedAgents.set(manifest.id, {
                    manifest,
                    filePath,
                    code,
                    language: entryFile.endsWith(".js") ? "js" : "python"
                });

                postMessage({ id, type: "LOAD_SUCCESS", agentId: manifest.id });
                break;
            }

            case "EXECUTE_AGENT": {
                const { agentId, task } = payload;
                const agent = loadedAgents.get(agentId);
                if (!agent) {
                    throw new Error(`런타임에 로드되지 않은 에이전트입니다: ${agentId}`);
                }

                const startTime = performance.now();
                let output = "";

                if (agent.language === "python") {
                    const runtime = await getPyodide();
                    
                    // 파이썬 전역 변수로 안전하게 task 전달 (문자열 이스케이프/줄바꿈 깨짐 방지)
                    runtime.globals.set("__task_input__", task);

                    const pyScript = `
import sys, importlib.util
from pathlib import Path

agent_file = Path('${agent.filePath}')
agent_dir = str(agent_file.parent)
if agent_dir not in sys.path:
    sys.path.insert(0, agent_dir)

spec = importlib.util.spec_from_file_location("mod_${agentId}", str(agent_file))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

if hasattr(mod, "run"):
    __res__ = str(mod.run(__task_input__))
else:
    __res__ = "오류: run(task) 함수를 찾을 수 없습니다."
`;
                    await runtime.runPythonAsync(pyScript);
                    output = runtime.globals.get("__res__");
                } else {
                    // JS 에이전트: run 함수 또는 직접 실행 처리
                    const fn = new Function("task", `${agent.code}\nreturn typeof run === 'function' ? run(task) : task;`);
                    output = await fn(task);
                }

                const durationMs = Math.round(performance.now() - startTime);
                postMessage({
                    id,
                    type: "EXECUTE_SUCCESS",
                    agentId,
                    output: String(output),
                    durationMs
                });
                break;
            }

            default:
                throw new Error(`알 수 없는 작업 타입: ${type}`);
        }
    } catch (err) {
        postMessage({
            id,
            type: "ERROR",
            error: err.message || String(err)
        });
    }
};
