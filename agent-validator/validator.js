/**
 * [AgentMarketPlatform] 3번 파트: 에이전트 표준 검증 엔진 & 패키징 빌더
 * 
 * 1. 에이전트 유형 판별:
 *    - TOOL (도구형): inputSchema, outputSchema, entrypoint, run()
 *    - AGENTIC (에이전틱 AI): prompt, requiredTools, modelRecommendation
 * 
 * 2. 2단계 검증 파이프라인:
 *    - 1단계: 구조 및 스키마 검사 (Structure Validation)
 *    - 2단계: 코드 보안 및 규제 준수 검사 (Security & Compliance - 피클 사태 방지 매크로 차단)
 *    - 3단계: 프롬프트 보안 검사 (Prompt Injection & Jailbreak Defense)
 * 
 * 3. 부가 기능:
 *    - 3단계 위험도(Risk Level: LOW, MEDIUM, CRITICAL) 자동 분류
 *    - 의존성 번들러 (Dependency Bundler): 에이전틱 에이전트의 필요 도구 묶음 처리
 *    - 다운로드 패키지 빌더 (buildDownloadPackage): LLM/MCP 즉시 연동 규격
 */

export const AgentType = {
    TOOL: "TOOL",         // LLM이 호출하는 단일 기능/함수형 도구
    AGENTIC: "AGENTIC"    // 자체 목표, 프롬프트, 도구 오케스트레이션을 갖춘 자율형 에이전트
};

export const RiskLevel = {
    LOW: "LOW",           // 단순 연산, 텍스트 요약 (자동 실행 허용)
    MEDIUM: "MEDIUM",     // 로컬 파일 읽기/저장 (알림 배너)
    CRITICAL: "CRITICAL"  // 결제, 예약, 개인정보, 외부 API 통신 (Human-in-the-Loop 승인 필수)
};

// 1. 시스템 파괴 위험 함수 (Critical Blocks)
export const BLOCKED_CALLS = [
    "eval(",
    "exec(",
    "compile(",
    "__import__(",
    "os.system",
    "os.popen",
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.check_output",
    "pty.spawn",
    "ctypes.",
    "pickle.loads",
    "marshal.loads"
];

// 2. [피클 기사 사안 반영] 비인가 매크로/웹 스크래핑 라이브러리 차단
export const BLOCKED_MACRO_MODULES = [
    "selenium",
    "playwright",
    "pyppeteer",
    "pyautogui",
    "pynput",
    "keyboard",
    "mouse",
    "splinter"
];

// 3. 프롬프트 인젝션 및 시스템 탈옥 위험 패턴 (Prompt Security)
export const BLOCKED_PROMPT_PATTERNS = [
    /ignore\s+(all\s+)?(previous|prior)\s+instructions/i,
    /system\s+prompt\s+override/i,
    /you\s+are\s+now\s+in\s+dan\s+mode/i,
    /jailbreak/i,
    /bypass\s+(security|safety|filter)/i,
    /출력\s*제한\s*무시/i,
    /이전\s*지시(사항)?\s*(무시|삭제)/i,
    /시스템\s*프롬프트(를)?\s*(유출|공개|출력)/i
];

export class AgentValidator {
    /**
     * [1단계] 구조 검사 (Structure Validation)
     */
    static validateStructure(manifest, code = "") {
        const errors = [];

        if (!manifest || typeof manifest !== "object") {
            return {
                valid: false,
                errors: ["manifest가 올바른 JSON 객체가 아닙니다."],
                type: AgentType.TOOL,
                normalizedManifest: null
            };
        }

        // 1. 공통 필수 메타데이터 검사
        if (!manifest.id || typeof manifest.id !== "string") {
            errors.push("에이전트 ID('id')가 누락되었거나 문자열이 아닙니다.");
        } else if (!/^[A-Za-z0-9_-]+$/.test(manifest.id)) {
            errors.push("에이전트 ID는 영문, 숫자, 하이픈(-), 밑줄(_)만 허용됩니다.");
        }

        if (!manifest.name || typeof manifest.name !== "string" || !manifest.name.trim()) {
            errors.push("에이전트 이름('name')이 올바르지 않습니다.");
        }

        if (typeof manifest.description !== "string") {
            errors.push("에이전트 설명('description')은 문자열이어야 합니다.");
        }

        // 2. 유형 판별 (기본값: TOOL)
        const rawType = (manifest.type || "TOOL").toUpperCase();
        const type = rawType === "AGENTIC" ? AgentType.AGENTIC : AgentType.TOOL;

        // 3. 유형별 상세 검증
        if (type === AgentType.TOOL) {
            const entrypoint = manifest.entrypoint || "agent.py";
            if (!entrypoint || typeof entrypoint !== "string") {
                errors.push("도구형 에이전트는 진입점('entrypoint') 파일명이 필요합니다.");
            }

            if (manifest.inputSchema && typeof manifest.inputSchema !== "object") {
                errors.push("도구형 에이전트의 inputSchema는 올바른 JSON Schema 객체여야 합니다.");
            }
            if (manifest.outputSchema && typeof manifest.outputSchema !== "object") {
                errors.push("도구형 에이전트의 outputSchema는 올바른 JSON Schema 객체여야 합니다.");
            }

            if (code && !code.includes("def run(") && !code.includes("function run(") && !code.includes("run =")) {
                errors.push("도구형 에이전트 코드에는 진입점 실행 함수 'run(task)'가 정의되어 있어야 합니다.");
            }

        } else if (type === AgentType.AGENTIC) {
            if (!manifest.prompt || typeof manifest.prompt !== "string" || !manifest.prompt.trim()) {
                errors.push("에이전틱 에이전트는 역할과 목표를 정의한 'prompt'(시스템 프롬프트)가 필수입니다.");
            }

            if (manifest.requiredTools && !Array.isArray(manifest.requiredTools)) {
                errors.push("에이전틱 에이전트의 필요 도구 목록('requiredTools')은 배열 형태여야 합니다.");
            }
        }

        // 4. 위험도 평가 (Risk Assessment)
        const riskLevel = this.assessRisk(manifest, code);

        const normalizedManifest = {
            id: manifest.id,
            name: manifest.name,
            version: manifest.version || "1.0.0",
            description: manifest.description || "",
            type: type,
            riskLevel: riskLevel,
            entrypoint: manifest.entrypoint || (type === AgentType.TOOL ? "agent.py" : null),
            prompt: manifest.prompt || null,
            requiredTools: Array.isArray(manifest.requiredTools) ? manifest.requiredTools : [],
            inputSchema: manifest.inputSchema || null,
            outputSchema: manifest.outputSchema || null,
            requiresConfirmation: riskLevel === RiskLevel.CRITICAL ? true : Boolean(manifest.requiresConfirmation),
            permissions: Array.isArray(manifest.permissions) ? manifest.permissions : [],
            compliance: manifest.compliance || { officialApiOnly: true }
        };

        return {
            valid: errors.length === 0,
            errors,
            type,
            normalizedManifest
        };
    }

    /**
     * [2단계] 코드 보안 및 규제 검사 (Security & Compliance)
     */
    static validateSecurity(code, manifest = {}) {
        const blockedReasons = [];
        const warnings = [];

        if (!code || typeof code !== "string") {
            return {
                passed: true,
                blockedReasons: [],
                warnings: ["검사할 소스 코드가 비어 있습니다."]
            };
        }

        // 1. 악성 시스템 호출 검사
        for (const pattern of BLOCKED_CALLS) {
            if (code.includes(pattern)) {
                blockedReasons.push(`[보안 차단] 위험한 시스템/동적 실행 코드 감지: '${pattern}'`);
            }
        }

        // 2. 피클 사태 방지: 비인가 매크로/스크래핑 라이브러리 검출
        for (const mod of BLOCKED_MACRO_MODULES) {
            const importRegex = new RegExp(`(^|\\n|;)\\s*(import\\s+${mod}|from\\s+${mod}\\b)`, "m");
            if (importRegex.test(code)) {
                blockedReasons.push(
                    `[정책 차단 - 기사 사안 반영] 비인가 웹 자동화/매크로 라이브러리('${mod}')는 플랫폼 차단 및 이용약관 위반 위험으로 업로드할 수 없습니다.`
                );
            }
        }

        return {
            passed: blockedReasons.length === 0,
            blockedReasons,
            warnings
        };
    }

    /**
     * [3단계] 프롬프트 보안 검사 (Prompt Security & Injection Defense)
     */
    static validatePrompt(prompt) {
        const findings = [];
        if (!prompt || typeof prompt !== "string") {
            return { passed: true, findings: [] };
        }

        for (const regex of BLOCKED_PROMPT_PATTERNS) {
            if (regex.test(prompt)) {
                findings.push(`[프롬프트 보안 차단] 악의적인 프롬프트 인젝션 또는 탈옥 패턴 감지: ${regex.source}`);
            }
        }

        return {
            passed: findings.length === 0,
            findings
        };
    }

    /**
     * 위험도 자동 산정 (LOW / MEDIUM / CRITICAL)
     */
    static assessRisk(manifest, code = "") {
        const criticalKeywords = ["pay", "payment", "book", "reserve", "order", "credential", "auth", "결제", "예약", "주문", "인증", "계좌"];
        const mediumKeywords = ["file", "save", "write", "storage", "저장", "파일"];

        const corpus = `${manifest.name || ""} ${manifest.description || ""} ${manifest.prompt || ""} ${code}`.toLowerCase();

        if (criticalKeywords.some(kw => corpus.includes(kw))) {
            return RiskLevel.CRITICAL;
        }
        if (mediumKeywords.some(kw => corpus.includes(kw))) {
            return RiskLevel.MEDIUM;
        }
        return RiskLevel.LOW;
    }

    /**
     * 종합 검사 (Structure + Security + Prompt)
     */
    static inspect(manifest, code = "") {
        // 1. 구조 검사
        const structure = this.validateStructure(manifest, code);
        if (!structure.valid) {
            return {
                success: false,
                stage: "STRUCTURE",
                structure,
                security: null,
                promptSecurity: null,
                summary: `1단계 구조 검사 실패: ${structure.errors.join("; ")}`
            };
        }

        // 2. 보안 검사
        const security = this.validateSecurity(code, structure.normalizedManifest);
        if (!security.passed) {
            return {
                success: false,
                stage: "SECURITY",
                structure,
                security,
                promptSecurity: null,
                summary: `2단계 보안 검사 실패: ${security.blockedReasons.join("; ")}`
            };
        }

        // 3. 프롬프트 보안 검사 (AGENTIC 에이전트인 경우)
        let promptSecurity = { passed: true, findings: [] };
        if (structure.type === AgentType.AGENTIC && structure.normalizedManifest.prompt) {
            promptSecurity = this.validatePrompt(structure.normalizedManifest.prompt);
            if (!promptSecurity.passed) {
                return {
                    success: false,
                    stage: "PROMPT_SECURITY",
                    structure,
                    security,
                    promptSecurity,
                    summary: `3단계 프롬프트 검사 실패: ${promptSecurity.findings.join("; ")}`
                };
            }
        }

        return {
            success: true,
            stage: "PASSED",
            structure,
            security,
            promptSecurity,
            summary: `에이전트 검증 통과 [유형: ${structure.type}, 위험도: ${structure.normalizedManifest.riskLevel}]`
        };
    }

    /**
     * 의존성 번들러 (Dependency Bundler)
     * 에이전틱 에이전트가 필요로 하는 하위 도구들을 묶어 단일 실행 번들로 조합
     */
    static bundleAgentDependencies(agenticManifest, availableToolsMap = {}) {
        if (agenticManifest.type !== AgentType.AGENTIC) {
            throw new Error("의존성 번들링은 AGENTIC 에이전트만 지원합니다.");
        }

        const requiredTools = agenticManifest.requiredTools || [];
        const bundledTools = [];
        const missingTools = [];

        for (const toolId of requiredTools) {
            if (availableToolsMap[toolId]) {
                bundledTools.push(availableToolsMap[toolId]);
            } else {
                missingTools.push(toolId);
            }
        }

        return {
            bundleId: `${agenticManifest.id}-bundle`,
            agent: agenticManifest,
            bundledTools,
            missingTools,
            isComplete: missingTools.length === 0,
            generatedAt: new Date().toISOString()
        };
    }

    /**
     * 다운로드용 표준 패키지(agent.json) 빌드
     */
    static buildDownloadPackage(manifest, code = "") {
        const inspection = this.inspect(manifest, code);
        if (!inspection.success) {
            throw new Error(`패키징 불가: ${inspection.summary}`);
        }

        const norm = inspection.structure.normalizedManifest;

        return {
            schemaVersion: "2.1.0",
            packageType: norm.type,
            riskLevel: norm.riskLevel,
            agent: {
                id: norm.id,
                name: norm.name,
                version: norm.version,
                description: norm.description,
                requiresConfirmation: norm.requiresConfirmation,
                permissions: norm.permissions,
                compliance: norm.compliance
            },
            toolBinding: norm.type === AgentType.TOOL ? {
                entrypoint: norm.entrypoint,
                inputSchema: norm.inputSchema || { type: "string", description: "작업 지시문" },
                outputSchema: norm.outputSchema || { type: "string", description: "실행 결과" }
            } : null,
            agenticBinding: norm.type === AgentType.AGENTIC ? {
                systemPrompt: norm.prompt,
                requiredTools: norm.requiredTools,
                recommendedModel: "gemini-2.5-flash / gpt-4o",
                executionMode: "autonomous-loop"
            } : null,
            code: code,
            validatedAt: new Date().toISOString()
        };
    }
}
