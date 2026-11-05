/**
 * Workflow Engine
 * - 여러 에이전트와 경량 LLM을 체이닝(Chaining)하여 순차적으로 실행하는 파이프라인 엔진
 * - 단계별 결과 전달, 컨텍스트 상태 관리, 실시간 진행 상태 이벤트 발생
 */

export class WorkflowEngine {
    constructor(agentRunner, llmEngine) {
        this.runner = agentRunner;
        this.llm = llmEngine;
        this.onStepStart = null;
        this.onStepComplete = null;
        this.onStepError = null;
    }

    /**
     * 순차 워크플로 실행
     * @param {Array<Object>} steps - 실행할 단계 목록
     *   예: [
     *     { type: 'agent', agentId: 'text_analyzer', label: '1단계: 텍스트 분석' },
     *     { type: 'llm', prompt: '다음 분석 결과를 바탕으로 핵심 결론을 요약해줘: {{prev}}', label: '2단계: LLM 요약' },
     *     { type: 'agent', agentId: 'demo_agent', label: '3단계: 최종 보고서 생성' }
     *   ]
     * @param {string} initialInput - 시작 입력 데이터
     * @returns {Promise<Array<Object>>} 단계별 실행 결과 기록
     */
    async executeWorkflow(steps, initialInput) {
        const history = [];
        let currentData = initialInput;

        for (let i = 0; i < steps.length; i++) {
            const step = steps[i];
            const startTime = performance.now();

            if (this.onStepStart) {
                this.onStepStart(i, step, currentData);
            }

            try {
                let output = "";

                if (step.type === "agent") {
                    // 에이전트 실행
                    const taskInput = step.inputTemplate 
                        ? step.inputTemplate.replace("{{prev}}", currentData)
                        : currentData;

                    const res = await this.runner.runAgent(step.agentId, taskInput);
                    output = res.result;

                } else if (step.type === "llm") {
                    // 브라우저 경량 LLM 실행
                    const prompt = step.prompt 
                        ? step.prompt.replace("{{prev}}", currentData)
                        : currentData;

                    output = await this.llm.generate(prompt);

                } else if (step.type === "custom") {
                    // 커스텀 변환 함수
                    output = await step.handler(currentData);
                } else {
                    throw new Error(`지원하지 않는 단계 타입: ${step.type}`);
                }

                const duration = Math.round(performance.now() - startTime);
                const stepResult = {
                    index: i,
                    label: step.label || `Step ${i + 1}`,
                    type: step.type,
                    input: currentData,
                    output: output,
                    durationMs: duration,
                    success: true
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

