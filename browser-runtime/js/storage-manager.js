/**
 * Storage Manager
 * - 에이전트 패키지(manifest, 코드, 무결성 해시)를 브라우저 IndexedDB에 영구 저장
 * - 모델 가중치 및 정적 에셋을 Cache API(CacheStorage)에 캐싱하여 오프라인/재방문 시 재다운로드 방지
 */

const DB_NAME = "AgentMarketDB";
const DB_VERSION = 1;
const STORE_AGENTS = "installed_agents";
const STORE_SETTINGS = "settings";
const CACHE_NAME = "agent-market-model-cache-v1";

export class StorageManager {
    constructor() {
        this.db = null;
    }

    /**
     * IndexedDB 초기화
     */
    async init() {
        if (this.db) return this.db;

        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onupgradeneeded = (event) => {
                const db = event.target.result;

                // 에이전트 패키지 저장소 (key: agentId)
                if (!db.objectStoreNames.contains(STORE_AGENTS)) {
                    const agentStore = db.createObjectStore(STORE_AGENTS, { keyPath: "id" });
                    agentStore.createIndex("installedAt", "installedAt", { unique: false });
                }

                // 일반 설정 저장소
                if (!db.objectStoreNames.contains(STORE_SETTINGS)) {
                    db.createObjectStore(STORE_SETTINGS, { keyPath: "key" });
                }
            };

            request.onsuccess = (event) => {
                this.db = event.target.result;
                resolve(this.db);
            };

            request.onerror = (event) => {
                reject(new Error(`IndexedDB 열기 실패: ${event.target.error}`));
            };
        });
    }

    /**
     * 에이전트 패키지를 IndexedDB에 저장/캐싱합니다.
     * @param {Object} packageData - { id, manifest, code, integrity, version }
     */
    async saveAgent(packageData) {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction([STORE_AGENTS], "readwrite");
            const store = tx.objectStore(STORE_AGENTS);

            const record = {
                id: packageData.id,
                manifest: packageData.manifest,
                code: packageData.code,
                integrity: packageData.integrity || null,
                version: packageData.version || "1.0.0",
                installedAt: Date.now()
            };

            const req = store.put(record);
            req.onsuccess = () => resolve(record);
            req.onerror = () => reject(req.error);
        });
    }

    /**
     * 저장된 특정 에이전트를 조회합니다.
     */
    async getAgent(agentId) {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction([STORE_AGENTS], "readonly");
            const store = tx.objectStore(STORE_AGENTS);
            const req = store.get(agentId);
            req.onsuccess = () => resolve(req.result || null);
            req.onerror = () => reject(req.error);
        });
    }

    /**
     * 저장된 모든 에이전트 목록을 조회합니다.
     */
    async getAllAgents() {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction([STORE_AGENTS], "readonly");
            const store = tx.objectStore(STORE_AGENTS);
            const req = store.getAll();
            req.onsuccess = () => resolve(req.result || []);
            req.onerror = () => reject(req.error);
        });
    }

    /**
     * 특정 에이전트를 삭제합니다.
     */
    async deleteAgent(agentId) {
        await this.init();
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction([STORE_AGENTS], "readwrite");
            const store = tx.objectStore(STORE_AGENTS);
            const req = store.delete(agentId);
            req.onsuccess = () => resolve(true);
            req.onerror = () => reject(req.error);
        });
    }

    /**
     * Cache API: 모델 가중치 파일 또는 대용량 에셋 캐싱
     */
    async cacheModelAsset(url) {
        if (!("caches" in window)) {
            console.warn("이 브라우저는 Cache API를 지원하지 않습니다.");
            return;
        }

        const cache = await caches.open(CACHE_NAME);
        const match = await cache.match(url);
        if (!match) {
            await cache.add(url);
        }
    }

    /**
     * 브라우저 저장소 사용량 및 할당량 확인
     */
    async getStorageEstimate() {
        if (navigator.storage && navigator.storage.estimate) {
            const estimate = await navigator.storage.estimate();
            const usedMB = (estimate.usage / (1024 * 1024)).toFixed(2);
            const quotaMB = (estimate.quota / (1024 * 1024)).toFixed(2);
            return {
                usageBytes: estimate.usage,
                quotaBytes: estimate.quota,
                usageMB: Number(usedMB),
                quotaMB: Number(quotaMB),
                percentage: ((estimate.usage / estimate.quota) * 100).toFixed(1)
            };
        }
        return null;
    }

    /**
     * 캐시 및 저장소 비우기
     */
    async clearAll() {
        await this.init();
        return new Promise(async (resolve, reject) => {
            const tx = this.db.transaction([STORE_AGENTS], "readwrite");
            tx.objectStore(STORE_AGENTS).clear();
            tx.oncomplete = async () => {
                if ("caches" in window) {
                    await caches.delete(CACHE_NAME);
                }
                resolve();
            };
            tx.onerror = () => reject(tx.error);
        });
    }
}

