/**
 * Agent Runner
 * - Web Worker(Pyodide)와 통신하여 브라우저 내에서 에이전트 패키지를 로드하고 실행하는 메인 인터페이스
 */

export class AgentRunner {
    constructor(workerScriptPath = "js/agent-worker.js") {
        this.workerScriptPath = workerScriptPath;
        this.worker = null;
        this.messageId = 0;
        this.pendingRequests = new Map();
        this.onStatusChange = null;
        this.onLog = null;
        this.isReady = false;
    }

    /**
     * Web Worker를 시작하고 초기화합니다.
     */
    async init() {
        if (this.isReady) return;

        return new Promise((resolve, reject) => {
            try {
                this.worker = new Worker(this.workerScriptPath);

                this.worker.onmessage = (event) => {
                    const { id, type, error, ...data } = event.data;

                    if (type === "STATUS") {
                        if (this.onStatusChange) this.onStatusChange(data.message);
                        return;
                    }

                    if (type === "LOG") {
                        if (this.onLog) this.onLog(data.level, data.text);
                        return;
                    }

                    if (!id || !this.pendingRequests.has(id)) return;

                    const { resolve: res, reject: rej } = this.pendingRequests.get(id);
                    this.pendingRequests.delete(id);

                    if (type === "ERROR") {
                        rej(new Error(error));
                    } else {
                        res(data);
                    }
                };

                this.worker.onerror = (err) => {
                    console.error("Worker error:", err);
                    if (this.onStatusChange) this.onStatusChange(`Worker 에러: ${err.message}`);
                };

                // Worker에 INIT 명령 전송
                this._send("INIT")
                    .then(() => {
                        this.isReady = true;
                        resolve();
                    })
                    .catch(reject);

            } catch (err) {
                reject(err);
            }
        });
    }

    _send(type, payload = {}) {
        const id = ++this.messageId;
        return new Promise((resolve, reject) => {
            this.pendingRequests.set(id, { resolve, reject });
            this.worker.postMessage({ id, type, payload });
        });
    }

    /**
     * 에이전트 패키지(manifest 및 코드)를 브라우저 런타임에 로드합니다.
     * @param {Object} manifest - manifest.json 내용 (id, name, description, entrypoint 등)
     * @param {string} code - agent.py (또는 JS) 소스 코드 문자열
     */
    async loadAgent(manifest, code) {
        if (!this.isReady) await this.init();
        return this._send("LOAD_AGENT", { manifest, code });
    }

    /**
     * 로드된 에이전트에 작업을 전달하여 실행합니다.
     * @param {string} agentId - 에이전트 ID
     * @param {string} task - 에이전트에 전달할 작업 지시문
     * @returns {Promise<{ result: string, durationMs: number }>}
     */
    async runAgent(agentId, task) {
        if (!this.isReady) await this.init();
        return this._send("RUN_AGENT", { agentId, task });
    }

    /**
     * 현재 로드된 에이전트 목록을 조회합니다.
     */
    async listAgents() {
        if (!this.isReady) await this.init();
        const res = await this._send("LIST_AGENTS");
        return res.agents;
    }

    /**
     * 워커를 종료합니다.
     */
    terminate() {
        if (this.worker) {
            this.worker.terminate();
            this.worker = null;
            this.isReady = false;
        }
    }
}

