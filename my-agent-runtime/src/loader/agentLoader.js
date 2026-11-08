/**
 * [1] AgentLoader
 * - 에이전트 패키지(JSON manifest, 코드) 파싱, ZIP 압축 해제, 스키마 검증, 상태 관리 및 Web Worker 격리 실행
 */

import JSZip from "jszip";

export const AgentState = {
    UNLOADED: "UNLOADED",
    LOADING: "LOADING",
    READY: "READY",
    RUNNING: "RUNNING",
    ERROR: "ERROR"
};

export class AgentLoader {
    constructor() {
        this.worker = null;
        this.messageCounter = 0;
        this.pendingRequests = new Map();
        this.agentRegistry = new Map(); // agentId -> { manifest, code, state, error, lastRunMs }
        this.onStatus = null;
        this.onLog = null;
        this.isWorkerReady = false;
    }

    /**
     * Web Worker 초기화
     */
    async initWorker() {
        if (this.isWorkerReady) return;

        return new Promise((resolve, reject) => {
            try {
                this.worker = new Worker(new URL("./agentWorker.js", import.meta.url), { type: "module" });

                this.worker.onmessage = (e) => {
                    const { id, type, error, ...data } = e.data;

                    if (type === "STATUS") {
                        if (this.onStatus) this.onStatus(data.message);
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
                    if (this.onStatus) this.onStatus(`Worker 에러: ${err.message}`);
                };

                this._send("INIT")
                    .then(() => {
                        this.isWorkerReady = true;
                        resolve();
                    })
                    .catch(reject);
            } catch (err) {
                reject(err);
            }
        });
    }

    _send(type, payload = {}) {
        const id = ++this.messageCounter;
        return new Promise((resolve, reject) => {
            this.pendingRequests.set(id, { resolve, reject });
            this.worker.postMessage({ id, type, payload });
        });
    }

    /**
     * 에이전트 manifest JSON 파싱 및 유효성 검사
     */
    parseManifest(manifestInput) {
        let manifest = manifestInput;
        if (typeof manifestInput === "string") {
            try {
                manifest = JSON.parse(manifestInput);
            } catch (e) {
                throw new Error("올바른 JSON 형식이 아닙니다: " + e.message);
            }
        }

        if (!manifest || typeof manifest !== "object") {
            throw new Error("에이전트 매니페스트 형식이 올바르지 않습니다.");
        }

        const requiredFields = ["id", "name", "description"];
        for (const field of requiredFields) {
            if (!manifest[field] || typeof manifest[field] !== "string") {
                throw new Error(`필수 필드가 누락되었거나 올바르지 않습니다: ${field}`);
            }
        }

        if (!/^[A-Za-z0-9_-]+$/.test(manifest.id)) {
            throw new Error("에이전트 ID는 영문, 숫자, 하이픈(-), 밑줄(_)만 허용됩니다.");
        }

        return {
            id: manifest.id,
            name: manifest.name,
            description: manifest.description,
            entrypoint: manifest.entrypoint || "agent.py",
            version: manifest.version || "1.0.0"
        };
    }

    /**
     * Web Crypto API를 이용한 SHA-256 무결성 검증
     */
    async verifyHash(content, expectedHash) {
        if (!expectedHash) return true;
        const encoder = new TextEncoder();
        const data = encoder.encode(content);
        const hashBuffer = await crypto.subtle.digest("SHA-256", data);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        const hashHex = hashArray.map(b => b.toString(16).padStart(2, "0")).join("");
        return hashHex.toLowerCase() === expectedHash.toLowerCase();
    }

    /**
     * ZIP 압축 파일로부터 에이전트 패키지 자동 압축 해제 및 파싱
     * @param {File|Blob|ArrayBuffer} fileOrBlob
     */
    async parseZipPackage(fileOrBlob) {
        const zip = await JSZip.loadAsync(fileOrBlob);

        let manifestEntry = null;
        let basePrefix = "";

        // manifest.json 파일 탐색
        zip.forEach((relativePath, file) => {
            if (!file.dir && relativePath.endsWith("manifest.json")) {
                manifestEntry = file;
                basePrefix = relativePath.slice(0, relativePath.lastIndexOf("manifest.json"));
            }
        });

        if (!manifestEntry) {
            throw new Error("ZIP 파일 내에 manifest.json이 존재하지 않습니다.");
        }

        const manifestText = await manifestEntry.async("string");
        const manifest = this.parseManifest(manifestText);

        const entryName = manifest.entrypoint || "agent.py";
        const entryFile = zip.file(basePrefix + entryName) || zip.file(entryName);

        if (!entryFile) {
            throw new Error(`ZIP 파일 내에 실행 진입점 파일(${entryName})이 없습니다.`);
        }

        const code = await entryFile.async("string");

        // 무결성 해시 검증 (integrity.json이 동봉된 경우)
        let integrity = null;
        const integrityFile = zip.file(basePrefix + "integrity.json") || zip.file("integrity.json");
        if (integrityFile) {
            try {
                const integrityText = await integrityFile.async("string");
                integrity = JSON.parse(integrityText);

                if (integrity.files && integrity.files[entryName]) {
                    const valid = await this.verifyHash(code, integrity.files[entryName]);
                    if (!valid) {
                        throw new Error(`패키지 파일(${entryName})의 SHA-256 무결성 검증 실패 (파일 변조 의심)`);
                    }
                }
            } catch (err) {
                console.warn("무결성 검사 경고:", err.message);
            }
        }

        return {
            id: manifest.id,
            manifest,
            code,
            integrity,
            version: manifest.version || "1.0.0"
        };
    }

    /**
     * 드래그한 개별 파일 목록(manifest.json + agent.py) 파싱
     * @param {FileList|Array<File>} fileList
     */
    async parseFiles(fileList) {
        let manifestFile = null;
        let codeFile = null;
        let integrityFile = null;

        for (const f of fileList) {
            if (f.name === "manifest.json") manifestFile = f;
            else if (f.name.endsWith(".py") || f.name.endsWith(".js")) codeFile = f;
            else if (f.name === "integrity.json") integrityFile = f;
        }

        if (!manifestFile) throw new Error("선택된 파일 중 manifest.json이 없습니다.");
        if (!codeFile) throw new Error("선택된 파일 중 코드 파일(.py 또는 .js)이 없습니다.");

        const manifestText = await manifestFile.text();
        const manifest = this.parseManifest(manifestText);
        const code = await codeFile.text();

        let integrity = null;
        if (integrityFile) {
            try {
                integrity = JSON.parse(await integrityFile.text());
            } catch {}
        }

        return {
            id: manifest.id,
            manifest,
            code,
            integrity,
            version: manifest.version || "1.0.0"
        };
    }

    /**
     * 패키지 등록 및 런타임에 로드
     * @param {Object} pkg - { manifest, code, integrity }
     */
    async loadPackage(pkg) {
        const parsedManifest = this.parseManifest(pkg.manifest);
        const agentId = parsedManifest.id;

        this.agentRegistry.set(agentId, {
            id: agentId,
            manifest: parsedManifest,
            code: pkg.code,
            integrity: pkg.integrity || null,
            state: AgentState.LOADING,
            error: null
        });

        try {
            await this.initWorker();
            await this._send("LOAD_AGENT", {
                manifest: parsedManifest,
                code: pkg.code
            });

            const current = this.agentRegistry.get(agentId);
            current.state = AgentState.READY;
            return current;
        } catch (err) {
            const current = this.agentRegistry.get(agentId);
            if (current) {
                current.state = AgentState.ERROR;
                current.error = err.message;
            }
            throw err;
        }
    }

    /**
     * 에이전트 작업 실행
     */
    async executeAgent(agentId, task, timeoutMs = 30000) {
        const agent = this.agentRegistry.get(agentId);
        if (!agent) {
            throw new Error(`등록되지 않은 에이전트입니다: ${agentId}`);
        }

        agent.state = AgentState.RUNNING;

        let timer = null;
        const timeoutPromise = new Promise((_, reject) => {
            timer = setTimeout(() => {
                reject(new Error(`에이전트 실행 시간 초과 (${timeoutMs / 1000}초)`));
            }, timeoutMs);
        });

        try {
            const execPromise = this._send("EXECUTE_AGENT", { agentId, task });
            const result = await Promise.race([execPromise, timeoutPromise]);
            clearTimeout(timer);

            agent.state = AgentState.READY;
            agent.lastRunMs = result.durationMs;
            return result;
        } catch (err) {
            clearTimeout(timer);
            agent.state = AgentState.ERROR;
            agent.error = err.message;
            throw err;
        }
    }

    /**
     * 등록된 모든 에이전트 목록 및 상태 조회
     */
    getAgentList() {
        return Array.from(this.agentRegistry.values()).map(a => ({
            id: a.id,
            name: a.manifest.name,
            description: a.manifest.description,
            state: a.state,
            version: a.manifest.version,
            lastRunMs: a.lastRunMs || 0
        }));
    }
}
