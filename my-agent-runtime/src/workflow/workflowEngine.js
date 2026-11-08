/**
 * [4] WorkflowEngine
 * - 에이전트 순차 연결(Chaining) 및 사용자 개입(Human-in-the-Loop) 제어 엔진
 * - 단계별 결과 전달, Human Approval 대기/수정, 중단(Abort) 제어
 */

export class WorkflowEngine {
    constructor(agentLoader, llmEngine) {
        this.loader = agentLoader;
        this.llm = llmEngine;
        this.isPaused = false;
        this.isAborted = false;

        // 이벤트 리스너 콜백
        this.onStepStart = null;
        this.onStepComplete = null;
        this.onStepError = null;
        this.onApprovalRequired = null; // (approvalContext: { stepIndex, step, output, resolve, reject }) => void
    }

    /**
     * 실행 중단 요청
     */
    abort() {
        this.isAborted = true;
    }

    /**
     * 워크플로 실행
     * @param {Array<Object>} steps - 단계 배열
     * @param {string} initialInput - 초기 시작 데이터
     */
    async run(steps, initialInput) {
        this.isAborted = false;
        const results = [];
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
                    const task = step.template ? step.template.replace("{{prev}}", currentData) : currentData;
                    const res = await this.loader.executeAgent(step.agentId, task);
                    output = res.output;

                } else if (step.type === "llm") {
                    const prompt = step.prompt ? step.prompt.replace("{{prev}}", currentData) : currentData;
                    output = await this.llm.generate(prompt);

                } else if (step.type === "transform") {
                    output = step.fn ? await step.fn(currentData) : currentData;

                } else {
                    throw new Error(`지원하지 않는 단계 타입: ${step.type}`);
                }

                // 2. Human-in-the-Loop (HITL) 사용자 승인/수정 대기
                if (step.requireApproval && this.onApprovalRequired) {
                    output = await new Promise((resolve, reject) => {
                        this.onApprovalRequired({
                            stepIndex: i,
                            step,
                            output,
                            resolve: (approvedData) => resolve(approvedData !== undefined ? approvedData : output),
                            reject: (reason) => reject(new Error(reason || "사용자가 단계를 거절했습니다."))
                        });
                    });
                }

                const durationMs = Math.round(performance.now() - startTime);
                const stepRecord = {
                    index: i,
                    label: step.label || `Step ${i + 1}`,
                    type: step.type,
                    input: currentData,
                    output: output,
                    durationMs,
                    success: true
                };

                results.push(stepRecord);
                currentData = output; // 다음 단계로 데이터 전달

                if (this.onStepComplete) {
                    this.onStepComplete(i, step, stepRecord);
                }

            } catch (err) {
                const durationMs = Math.round(performance.now() - startTime);
                const errorRecord = {
                    index: i,
                    label: step.label || `Step ${i + 1}`,
                    type: step.type,
                    input: currentData,
                    error: err.message || String(err),
                    durationMs,
                    success: false
                };
                results.push(errorRecord);

                if (this.onStepError) {
                    this.onStepError(i, step, errorRecord);
                }
                throw err;
            }
        }

        return results;
    }
}

