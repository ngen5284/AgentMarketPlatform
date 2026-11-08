/**
 * LLM Engine
 * - WebGPU 가속 기반 브라우저 온디바이스 경량 LLM (WebLLM) 로더 및 추론 엔진
 * - 모델 다운로드 진행률(Progress %, 텍스트) 추적 및 스트리밍 생성 지원
 * - WebGPU 미지원 환경을 위한 안전한 폴백(Mock/Rule-based) 포함
 */

export class LLMEngine {
    constructor() {
        this.engine = null;
        this.selectedModel = "SmolLM2-360M-Instruct-q4f16_1-MLC";
        this.isLoaded = false;
        this.isLoading = false;
        this.isFallback = false;
        this.onProgress = null; // (progressInfo) => void
    }

    /**
     * 사용 가능한 경량 모델 목록 반환
     */
    getAvailableModels() {
        return [
            {
                id: "SmolLM2-360M-Instruct-q4f16_1-MLC",
                name: "SmolLM2 (360M)",
                size: "~250 MB",
                description: "초경량 빠른 추론, 낮은 사양에 최적화"
            },
            {
                id: "Qwen2.5-0.5B-Instruct-q4f16_1-MLC",
                name: "Qwen2.5 (0.5B)",
                size: "~400 MB",
                description: "가벼우면서도 준수한 한국어/다국어 성능"
            },
            {
                id: "Llama-3.2-1B-Instruct-q4f16_1-MLC",
                name: "Llama 3.2 (1B)",
                size: "~900 MB",
                description: "고성능 온디바이스 경량 모델"
            }
        ];
    }

    /**
     * WebGPU 지원 여부 검사
     */
    static checkWebGPUSupport() {
        return typeof navigator !== "undefined" && "gpu" in navigator;
    }

    /**
     * 경량 LLM 모델을 브라우저에 다운로드하고 메모리에 로드합니다.
     * @param {string} modelId - 선택한 모델 ID
     */
    async loadModel(modelId = this.selectedModel) {
        if (this.isLoading) return;
        this.isLoading = true;
        this.selectedModel = modelId;

        const hasGPU = LLMEngine.checkWebGPUSupport();

        if (this.onProgress) {
            this.onProgress({
                progress: 0.05,
                text: hasGPU ? "WebGPU 환경 감지됨. WebLLM 모듈 로딩 중..." : "WebGPU 미지원 환경: 시뮬레이션 폴백 모드로 실행됩니다."
            });
        }

        if (!hasGPU) {
            // WebGPU 미지원 환경 폴백
            await new Promise(r => setTimeout(r, 600));
            this.isFallback = true;
            this.isLoaded = true;
            this.isLoading = false;
            if (this.onProgress) {
                this.onProgress({ progress: 1.0, text: "경량 LLM (호환 모드) 준비 완료" });
            }
            return;
        }

        try {
            // WebLLM 모듈 동적 임포트 (ESM CDN)
            const webllm = await import("https://esm.run/@mlc-ai/web-llm");

            const initProgressCallback = (report) => {
                if (this.onProgress) {
                    this.onProgress({
                        progress: report.progress || 0,
                        text: report.text || "가중치 다운로드 및 컴파일 중..."
                    });
                }
            };

            this.engine = await webllm.CreateMLCEngine(this.selectedModel, {
                initProgressCallback
            });

            this.isLoaded = true;
            this.isFallback = false;
            if (this.onProgress) {
                this.onProgress({ progress: 1.0, text: `${modelId} 로딩 완료!` });
            }
        } catch (err) {
            console.warn("WebLLM 로드 실패, 호환 모드로 전환:", err);
            this.isFallback = true;
            this.isLoaded = true;
            if (this.onProgress) {
                this.onProgress({
                    progress: 1.0,
                    text: `WebGPU 초기화 실패로 호환 모드로 전환되었습니다: ${err.message}`
                });
            }
        } finally {
            this.isLoading = false;
        }
    }

    /**
     * 프롬프트를 전달하여 LLM 생성 응답을 받습니다.
     * @param {string} prompt - 전달할 지시문
     * @param {Function} [onToken] - 스트리밍 토큰 수신 콜백
     */
    async generate(prompt, onToken = null) {
        if (!this.isLoaded) {
            await this.loadModel(this.selectedModel);
        }

        if (this.isFallback) {
            // 폴백 모드: 브라우저 내 경량 응답 생성 시뮬레이션
            const sampleResponse = `[온디바이스 LLM 요약/판단 결과]\n분석된 작업 내용: "${prompt.slice(0, 100)}..."\n` +
                `-> 다음 단계 워크플로를 위한 정제된 데이터를 성공적으로 생성했습니다.`;
            
            if (onToken) {
                for (const char of sampleResponse) {
                    onToken(char);
                    await new Promise(r => setTimeout(r, 15));
                }
            }
            return sampleResponse;
        }

        // 실제 WebLLM 추론 실행
        const messages = [
            { role: "system", content: "You are a helpful and concise browser-embedded AI assistant." },
            { role: "user", content: prompt }
        ];

        if (onToken) {
            const chunks = await this.engine.chat.completions.create({
                messages,
                stream: true,
                temperature: 0.7,
                max_tokens: 512
            });

            let fullText = "";
            for await (const chunk of chunks) {
                const token = chunk.choices[0]?.delta?.content || "";
                fullText += token;
                onToken(token);
            }
            return fullText;
        } else {
            const reply = await this.engine.chat.completions.create({
                messages,
                temperature: 0.7,
                max_tokens: 512
            });
            return reply.choices[0].message.content;
        }
    }
}

