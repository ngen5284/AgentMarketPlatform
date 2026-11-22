/**
 * Agent Runner
 * - Web Worker(Pyodide)와 통신하여 브라우저 내에서 에이전트 패키지를 로드하고 실행하는 메인 인터페이스
 * - 에이전트 2단계 검증(구조 검사 -> 보안 검사) 수행
 * - [피클 기사 사안 반영] 실행 타임아웃, 호출 레이트리밋(Throttle), Human-in-the-Loop 연동
 */

import { AgentValidator, AgentType } from "./agent-validator.js";

export class AgentRunner {
    constructor(workerScriptPath = "js/agent-worker.js") {
        this.workerScriptPath = workerScriptPath;
        this.worker = null;
        this.messageId = 0;
        this.pendingRequests = new Map();
        this.onStatusChange = null;
        this.onLog = null;
        this.isReady = false;

        // 에이전트 메타데이터 및 상태 저장소
        this.loadedAgents = new Map(); // agentId -> { manifest, code, inspection, lastExecutedAt }
        this.defaultTimeoutMs = 20000;  // 20초 기본 타임아웃 (무한 루프 방지)
        this.defaultThrottleMs = 500;   // 500ms 기본 쿨다운 (매크로성 초단타 호출 방지)
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

                    const req = this.pendingRequests.get(id);
                    if (req.timer) clearTimeout(req.timer);
                    this.pendingRequests.delete(id);

                    if (type === "ERROR") {
                        req.reject(new Error(error));
                    } else {
                        req.resolve(data);
                    }
                };

                this.worker.onerror = (err) => {
                    console.error("Worker error:", err);
                    if (this.onStatusChange) this.onStatusChange(`Worker 에러: ${err.message}`);
                };

                // Worker에 INIT 명령 전송
                this._send("INIT", {}, 60000) // Pyodide 첫 로딩은 최대 60초 대기
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

    _send(type, payload = {}, timeoutMs = this.defaultTimeoutMs) {
        const id = ++this.messageId;
        return new Promise((resolve, reject) => {
            let timer = null;
            if (timeoutMs > 0) {
                timer = setTimeout(() => {
                    if (this.pendingRequests.has(id)) {
                        this.pendingRequests.delete(id);
                        reject(new Error(`요청 시간 초과 (${timeoutMs}ms) - 무한 루프 또는 응답 지연 감지`));
                    }
                }, timeoutMs);
            }

            this.pendingRequests.set(id, { resolve, reject, timer });
            this.worker.postMessage({ id, type, payload });
        });
    }

    /**
     * 에이전트 패키지 2단계 검증(구조 검사 -> 보안 검사) 수행
     * @param {Object} manifest 
     * @param {string} code 
     * @returns {Object} 검증 결과
     */
    validateAgent(manifest, code) {
        return AgentValidator.inspect(manifest, code);
    }

    /**
     * 에이전트 패키지를 검증 후 런타임에 로드합니다.
     * @param {Object} manifest - manifest.json 객체
     * @param {string} code - agent.py (또는 JS) 소스 코드 문자열
     * @param {boolean} [bypassValidation=false] - 검증 우회 여부
     */
    async loadAgent(manifest, code, bypassValidation = false) {
        if (!this.isReady) await this.init();

        let normalizedManifest = manifest;
        let inspection = null;

        if (!bypassValidation) {
            inspection = AgentValidator.inspect(manifest, code);
            if (!inspection.success) {
                throw new Error(`에이전트 패키지 검증 실패: ${inspection.summary}`);
            }
            normalizedManifest = inspection.structure.normalizedManifest;

            if (inspection.security.warnings.length > 0) {
                inspection.security.warnings.forEach(warn => {
                    if (this.onLog) this.onLog("warn", warn);
                });
            }
        }

        const res = await this._send("LOAD_AGENT", { manifest: normalizedManifest, code });

        this.loadedAgents.set(normalizedManifest.id, {
            manifest: normalizedManifest,
            code,
            inspection,
            lastExecutedAt: 0
        });

        return res;
    }

    /**
     * 로드된 에이전트에 작업을 전달하여 실행합니다.
     * [피클 기사 사안 반영] 무한 루프 타임아웃 및 매크로 방지 쿨다운 적용
     * @param {string} agentId - 에이전트 ID
     * @param {string} task - 작업 지시문
     * @param {Object} [options] - 실행 옵션
     * @param {number} [options.timeoutMs] - 실행 제한 시간 (ms)
     * @param {number} [options.throttleMs] - 최소 연속 호출 간격 (ms)
     */
    async runAgent(agentId, task, options = {}) {
        if (!this.isReady) await this.init();

        const agentEntry = this.loadedAgents.get(agentId);
        const timeoutMs = options.timeoutMs || this.defaultTimeoutMs;
        const throttleMs = options.throttleMs !== undefined ? options.throttleMs : this.defaultThrottleMs;

        // 1. 매크로성 초단타 반복 호출 방지 (Throttle / Anti-Macro)
        if (agentEntry && throttleMs > 0) {
            const now = performance.now();
            const elapsed = now - agentEntry.lastExecutedAt;
            if (elapsed < throttleMs) {
                const waitTime = Math.ceil(throttleMs - elapsed);
                await new Promise(r => setTimeout(r, waitTime));
            }
            agentEntry.lastExecutedAt = performance.now();
        }

        // 2. 타임아웃이 적용된 실행 요청
        return this._send("RUN_AGENT", { agentId, task }, timeoutMs);
    }

    /**
     * 다운로드용 표준 실행 패키지(agent.json) 생성
     * @param {string} agentId 
     */
    exportPackage(agentId) {
        const entry = this.loadedAgents.get(agentId);
        if (!entry) throw new Error(`에이전트를 찾을 수 없습니다: ${agentId}`);
        return AgentValidator.buildDownloadPackage(entry.manifest, entry.code);
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
            this.pendingRequests.clear();
        }
    }
}
