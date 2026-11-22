/**
 * Workflow Engine
 * - 여러 에이전트와 경량 LLM을 체이닝(Chaining)하여 순차적으로 실행하는 파이프라인 엔진
 * - [피클 기사 사안 반영] Human-in-the-Loop(인간 승인/교정 게이트) 및 파이프라인 중단(Abort) 제어
 */

export class WorkflowEngine {
    constructor(agentRunner, llmEngine) {
        this.runner = agentRunner;
        this.llm = llmEngine;
        this.isAborted = false;

        // 이벤트 리스너 콜백
        this.onStepStart = null;
        this.onStepComplete = null;
        this.onStepError = null;

        // Human-in-the-Loop 승인 요청 콜백
        // 시그니처: ({ stepIndex, step, output, resolve, reject }) => void
        this.onApprovalRequired = null;
    }

    /**
     * 실행 중인 워크플로 중단 요청
     */
    abort() {
        this.isAborted = true;
    }

    /**
     * 순차 워크플로 실행
     * @param {Array<Object>} steps - 실행할 단계 목록
     *   예: [
     *     { type: 'agent', agentId: 'text_analyzer', label: '1단계: 텍스트 분석' },
     *     { type: 'llm', prompt: '다음 분석 결과를 바탕으로 핵심 결론을 요약해줘: {{prev}}', label: '2단계: LLM 요약', requireApproval: true },
     *     { type: 'agent', agentId: 'demo_agent', label: '3단계: 최종 보고서 생성' }
     *   ]
     * @param {string} initialInput - 시작 입력 데이터
     * @param {Object} [options] - 실행 옵션
     * @returns {Promise<Array<Object>>} 단계별 실행 결과 기록
     */
    async executeWorkflow(steps, initialInput, options = {}) {
        this.isAborted = false;
        const history = [];
        let currentData = initialInput;

        for (let i = 0; i < steps.length; i++) {
            if (this.isAborted) {
                throw new Error("사용자에 의해 워크플로가 중단되었습니다.");
            }

            const step = steps[i];
            const startTime = performance.now();

            if (this.onStepStart) {
                this.onStepStart(i, step, currentData);
            }

            try {
                let output = "";

                // 1. 단계별 실행
                if (step.type === "agent") {
                    const taskInput = step.inputTemplate 
                        ? step.inputTemplate.replace("{{prev}}", currentData)
                        : currentData;

                    const timeoutMs = step.timeoutMs || options.stepTimeoutMs;
                    const res = await this.runner.runAgent(step.agentId, taskInput, { timeoutMs });
                    output = res.result;

                } else if (step.type === "llm") {
                    const prompt = step.prompt 
                        ? step.prompt.replace("{{prev}}", currentData)
                        : currentData;

                    output = await this.llm.generate(prompt);

                } else if (step.type === "custom") {
                    output = await step.handler(currentData);

                } else {
                    throw new Error(`지원하지 않는 단계 타입: ${step.type}`);
                }

                // 2. [기사 사안 반영] Human-in-the-Loop: 중요 단계 사용자 검토 및 승인 대기
                if (step.requireApproval && this.onApprovalRequired) {
                    output = await new Promise((resolve, reject) => {
                        this.onApprovalRequired({
                            stepIndex: i,
                            step,
                            output,
                            resolve: (approvedData) => {
                                // 사용자가 수정한 데이터가 있으면 수정본으로 다음 단계 진행
                                resolve(approvedData !== undefined ? approvedData : output);
                            },
                            reject: (reason) => {
                                this.abort();
                                reject(new Error(reason || "사용자가 단계를 거절하여 워크플로가 중단되었습니다."));
                            }
                        });
                    });
                }

                const duration = Math.round(performance.now() - startTime);
                const stepResult = {
                    index: i,
                    label: step.label || `Step ${i + 1}`,
                    type: step.type,
                    input: currentData,
                    output: output,
                    durationMs: duration,
                    success: true,
                    approvedByUser: Boolean(step.requireApproval)
                };

                history.push(stepResult);
                currentData = output; // 다음 단계로 출력 전달

                if (this.onStepComplete) {
                    this.onStepComplete(i, step, stepResult);
                }

            } catch (err) {
                const duration = Math.round(performance.now() - startTime);
                const errorResult = {
                    index: i,
                    label: step.label || `Step ${i + 1}`,
                    type: step.type,
                    input: currentData,
                    error: err.message || String(err),
                    durationMs: duration,
                    success: false
                };

                history.push(errorResult);

                if (this.onStepError) {
                    this.onStepError(i, step, errorResult);
                }

                throw new Error(`워크플로 [${step.label || i + 1}단계] 실패: ${err.message}`);
            }
        }

        return history;
    }
}
