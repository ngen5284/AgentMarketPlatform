/**
 * [2] IndexedDbCache
 * - IndexedDB 및 Cache API를 이용한 에이전트 패키지, 워크플로 기록, 모델 가중치 오프라인 캐싱 관리자
 */

const DB_NAME = "AgentMarketRuntimeDB";
const DB_VERSION = 1;

const STORES = {
    AGENTS: "agents",
    WORKFLOWS: "workflows",
    MODEL_CACHE: "model_cache"
};

const CACHE_STORAGE_KEY = "agent-runtime-weights-v1";

export class IndexedDbCache {
    constructor() {
        this.db = null;
    }

    /**
     * IndexedDB 초기화 및 테이블 생성
     */
    async init() {
        if (this.db) return this.db;

        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onupgradeneeded = (e) => {
                const db = e.target.result;

                // 1. 에이전트 패키지 저장소
                if (!db.objectStoreNames.contains(STORES.AGENTS)) {
                    const agentStore = db.createObjectStore(STORES.AGENTS, { keyPath: "id" });
                    agentStore.createIndex("updatedAt", "updatedAt", { unique: false });
                }

                // 2. 워크플로 실행 이력 저장소
                if (!db.objectStoreNames.contains(STORES.WORKFLOWS)) {
                    const wfStore = db.createObjectStore(STORES.WORKFLOWS, { keyPath: "id", autoIncrement: true });
                    wfStore.createIndex("timestamp", "timestamp", { unique: false });
                }

                // 3. 모델 캐시 메타데이터 저장소
                if (!db.objectStoreNames.contains(STORES.MODEL_CACHE)) {
                    db.createObjectStore(STORES.MODEL_CACHE, { keyPath: "modelId" });
                }
            };

            request.onsuccess = (e) => {
                this.db = e.target.result;
                resolve(this.db);
            };

            request.onerror = (e) => {
                reject(new Error(`IndexedDB 열기 실패: ${e.target.error}`));
            };
        });
    }

    /**
     * 에이전트 패키지 캐싱 저장
     * @param {Object} agentPackage - { id, manifest, code, integrity, version }
     */
    async saveAgent(agentPackage) {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction([STORES.AGENTS], "readwrite");
            const store = tx.objectStore(STORES.AGENTS);

            const record = {
                ...agentPackage,
                updatedAt: Date.now()
            };

            const req = store.put(record);
            req.onsuccess = () => resolve(record);
            req.onerror = () => reject(req.error);
        });
    }

    /**
     * 특정 에이전트 패키지 조회
     */
    async getAgent(agentId) {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction([STORES.AGENTS], "readonly");
            const store = tx.objectStore(STORES.AGENTS);
            const req = store.get(agentId);
            req.onsuccess = () => resolve(req.result || null);
            req.onerror = () => reject(req.error);
        });
    }

    /**
     * 캐시된 모든 에이전트 목록 반환
     */
    async getAllAgents() {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction([STORES.AGENTS], "readonly");
            const store = tx.objectStore(STORES.AGENTS);
            const req = store.getAll();
            req.onsuccess = () => resolve(req.result || []);
            req.onerror = () => reject(req.error);
        });
    }

    /**
     * 에이전트 삭제
     */
    async deleteAgent(agentId) {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction([STORES.AGENTS], "readwrite");
            const store = tx.objectStore(STORES.AGENTS);
            const req = store.delete(agentId);
            req.onsuccess = () => resolve(true);
            req.onerror = () => reject(req.error);
        });
    }

    /**
     * 워크플로 실행 이력 저장
     */
    async saveWorkflowHistory(historyData) {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction([STORES.WORKFLOWS], "readwrite");
            const store = tx.objectStore(STORES.WORKFLOWS);
            const req = store.add({
                ...historyData,
                timestamp: Date.now()
            });
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    }

    /**
     * 최근 워크플로 실행 이력 조회
     */
    async getWorkflowHistories(limit = 10) {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction([STORES.WORKFLOWS], "readonly");
            const store = tx.objectStore(STORES.WORKFLOWS);
            const req = store.getAll();
            req.onsuccess = () => {
                const list = req.result || [];
                resolve(list.sort((a, b) => b.timestamp - a.timestamp).slice(0, limit));
            };
            req.onerror = () => reject(req.error);
        });
    }

    /**
     * 브라우저 저장소 사용량 및 잔여 용량 계산 (MB 단위)
     */
    async estimateStorage() {
        if (navigator.storage && navigator.storage.estimate) {
            const est = await navigator.storage.estimate();
            const usageMB = (est.usage / (1024 * 1024)).toFixed(2);
            const quotaMB = (est.quota / (1024 * 1024)).toFixed(2);
            const percent = ((est.usage / est.quota) * 100).toFixed(1);
            return {
                usageMB: Number(usageMB),
                quotaMB: Number(quotaMB),
                percentage: percent
            };
        }
        return { usageMB: 0, quotaMB: 0, percentage: "0.0" };
    }

    /**
     * 전체 저장소 캐시 초기화
     */
    async clearAll() {
        await this.init();
        return new Promise(async (resolve, reject) => {
            try {
                const tx = this.db.transaction([STORES.AGENTS, STORES.WORKFLOWS, STORES.MODEL_CACHE], "readwrite");
                tx.objectStore(STORES.AGENTS).clear();
                tx.objectStore(STORES.WORKFLOWS).clear();
                tx.objectStore(STORES.MODEL_CACHE).clear();

                if ("caches" in window) {
                    await caches.delete(CACHE_STORAGE_KEY);
                }

                tx.oncomplete = () => resolve(true);
                tx.onerror = () => reject(tx.error);
            } catch (err) {
                reject(err);
            }
        });
    }
}

