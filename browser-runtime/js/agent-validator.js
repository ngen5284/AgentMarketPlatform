/**
 * Agent Validator (에이전트 2단계 검증 모듈)
 * 
 * 1단계: 구조 검사 (Structure Validation)
 *   - 에이전트 유형 판별: 'TOOL' (도구형) vs 'AGENTIC' (에이전틱 AI 에이전트)
 *   - 필수 필드, 명칭, ID 규격, 파일 진입점 검사
 *   - 스키마 유효성: TOOL의 inputSchema/outputSchema, AGENTIC의 prompt/requiredTools
 * 
 * 2단계: 보안 검사 (Security & Compliance Inspection)
 *   - 시스템 악성 코드 차단: os.system, subprocess, eval, exec 등
 *   - [피클 기사 반영] 비인가 매크로/스크래핑 라이브러리 차단: selenium, playwright, pyautogui 등
 *   - 중요 액션에 대한 Human-in-the-Loop (requiresConfirmation) 설정 여부 검사
 */

export const AgentType = {
    TOOL: "TOOL",         // LLM이 호출하는 기능/도구형 에이전트
    AGENTIC: "AGENTIC"    // 자체 추론 루프와 프롬프트를 가진 자율형 AI 에이전트
};

// 1. 차단 대상 시스템 호출/함수 (Critical Block)
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

// 2. [기사 반영] 피클 사태 방지용 비인가 웹 매크로/스크래핑 모듈 차단
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

// 3. 주의/경고 대상 모듈 및 함수
export const WARNING_CALLS = [
    "requests.Session",
    "urllib.request",
    "importlib.",
    "yaml.load"
];

export class AgentValidator {
    /**
     * 1단계: 구조 검사 (Structure Validation)
     * @param {Object} manifest - manifest.json 객체
     * @param {string} [code=""] - 에이전트 코드 (선택)
     * @returns {{ valid: boolean, errors: string[], type: string, normalizedManifest: Object }}
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

        // 기본 필수 필드 검사
        if (!manifest.id || typeof manifest.id !== "string") {
            errors.push("에이전트 ID('id')가 누락되었거나 문자열이 아닙니다.");
        } else if (!/^[A-Za-z0-9_-]+$/.test(manifest.id)) {
            errors.push("에이전트 ID는 영문 대소문자, 숫자, 하이픈(-), 밑줄(_)만 허용됩니다.");
        }

        if (!manifest.name || typeof manifest.name !== "string" || !manifest.name.trim()) {
            errors.push("에이전트 이름('name')이 올바르지 않습니다.");
        }

        if (typeof manifest.description !== "string") {
            errors.push("에이전트 설명('description')은 문자열이어야 합니다.");
        }

        // 에이전트 타입 결정 (기본값: TOOL)
        const rawType = (manifest.type || "TOOL").toUpperCase();
        const type = rawType === "AGENTIC" ? AgentType.AGENTIC : AgentType.TOOL;

        // 타입별 상세 구조 검사
        if (type === AgentType.TOOL) {
            // 도구형 에이전트 검사
            const entrypoint = manifest.entrypoint || "agent.py";
            if (!entrypoint || typeof entrypoint !== "string") {
                errors.push("도구형 에이전트는 진입점('entrypoint') 파일명이 필요합니다.");
            }

            // inputSchema / outputSchema 검증 (제공된 경우)
            if (manifest.inputSchema && typeof manifest.inputSchema !== "object") {
                errors.push("도구형 에이전트의 inputSchema는 올바른 JSON 객체여야 합니다.");
            }
            if (manifest.outputSchema && typeof manifest.outputSchema !== "object") {
                errors.push("도구형 에이전트의 outputSchema는 올바른 JSON 객체여야 합니다.");
            }

            // 코드 내 run 함수 존재 여부 간이 검사
            if (code && !code.includes("def run(") && !code.includes("function run(") && !code.includes("run =")) {
                errors.push("도구형 에이전트 코드에는 진입점 실행 함수 'run(task)'가 정의되어 있어야 합니다.");
            }

        } else if (type === AgentType.AGENTIC) {
            // 에이전틱 AI 에이전트 검사
            if (!manifest.prompt || typeof manifest.prompt !== "string" || !manifest.prompt.trim()) {
                errors.push("에이전틱 에이전트는 목표 및 페르소나가 담긴 시스템 프롬프트('prompt')가 필수입니다.");
            }

            if (manifest.requiredTools && !Array.isArray(manifest.requiredTools)) {
                errors.push("에이전틱 에이전트의 필요 도구 목록('requiredTools')은 배열 형태여야 합니다.");
            }
        }

        const normalizedManifest = {
            id: manifest.id,
            name: manifest.name,
            version: manifest.version || "1.0.0",
            description: manifest.description || "",
            type: type,
            entrypoint: manifest.entrypoint || (type === AgentType.TOOL ? "agent.py" : null),
            prompt: manifest.prompt || null,
            requiredTools: Array.isArray(manifest.requiredTools) ? manifest.requiredTools : [],
            inputSchema: manifest.inputSchema || null,
            outputSchema: manifest.outputSchema || null,
            requiresConfirmation: Boolean(manifest.requiresConfirmation),
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
     * 2단계: 보안 검사 (Security & Policy Inspection)
     * 피클 사태 방지를 위해 비인가 매크로/스크래핑 라이브러리 및 시스템 파괴 코드 검출
     * @param {string} code - 검사할 소스 코드 문자열
     * @param {Object} [manifest={}] - manifest 정보
     * @returns {{ passed: boolean, blockedReasons: string[], warnings: string[] }}
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

        // 1. 시스템 악성 호출 검사
        for (const pattern of BLOCKED_CALLS) {
            if (code.includes(pattern)) {
                blockedReasons.push(`[보안 차단] 위험한 시스템 또는 동적 코드 실행 호출 감지: '${pattern}'`);
            }
        }

        // 2. [기사 반영] 피클 사태 방지: 비인가 매크로/웹 스크래핑 라이브러리 검출
        for (const mod of BLOCKED_MACRO_MODULES) {
            const importRegex = new RegExp(`(^|\\n|;)\\s*(import\\s+${mod}|from\\s+${mod}\\b)`, "m");
            if (importRegex.test(code)) {
                blockedReasons.push(
                    `[정책 차단 - 기사 사안 반영] 비인가 웹 자동화/매크로 라이브러리('${mod}')는 차단 솔루션 탐지 및 플랫폼 약관 위반 위험으로 업로드할 수 없습니다.`
                );
            }
        }

        // 3. 주의/경고 대상 검사
        for (const warn of WARNING_CALLS) {
            if (code.includes(warn)) {
                warnings.push(`[보안 주의] 외부 요청 또는 동적 모듈 사용이 감지되었습니다: '${warn}'`);
            }
        }

        // 4. 결제/예약 등 중요 액션인데 Human-in-the-Loop(승인) 선언이 누락된 경우 경고
        const sensitiveKeywords = ["pay", "payment", "book", "reserve", "order", "결제", "예약", "주문"];
        const hasSensitiveAction = sensitiveKeywords.some(kw => 
            (manifest.name && manifest.name.toLowerCase().includes(kw)) ||
            (manifest.description && manifest.description.toLowerCase().includes(kw)) ||
            code.toLowerCase().includes(kw)
        );

        if (hasSensitiveAction && !manifest.requiresConfirmation) {
            warnings.push(
                "[안전 권고] 결제/예약 등 민감한 동작이 감지되었으나 'requiresConfirmation: true'가 선언되지 않았습니다. 사용자 승인 게이트 설정을 강력히 권장합니다."
            );
        }

        return {
            passed: blockedReasons.length === 0,
            blockedReasons,
            warnings
        };
    }

    /**
     * 통합 2단계 검증 실행
     * @param {Object} manifest 
     * @param {string} code 
     * @returns {{ success: boolean, structure: Object, security: Object, summary: string }}
     */
    static inspect(manifest, code) {
        const structure = this.validateStructure(manifest, code);
        if (!structure.valid) {
            return {
                success: false,
                stage: "STRUCTURE",
                structure,
                security: null,
                summary: `1단계 구조 검사 실패: ${structure.errors.join("; ")}`
            };
        }

        const security = this.validateSecurity(code, structure.normalizedManifest);
        if (!security.passed) {
            return {
                success: false,
                stage: "SECURITY",
                structure,
                security,
                summary: `2단계 보안 검사 실패: ${security.blockedReasons.join("; ")}`
            };
        }

        return {
            success: true,
            stage: "PASSED",
            structure,
            security,
            summary: `에이전트 검증 통과 [유형: ${structure.type}] (경고 ${security.warnings.length}건)`
        };
    }

    /**
     * 다운로드용 표준 패키지(agent.json) 빌드
     * "다운받아서 LLM을 붙이는 실행 인터페이스"
     */
    static buildDownloadPackage(manifest, code) {
        const inspection = this.inspect(manifest, code);
        if (!inspection.success) {
            throw new Error(`패키징 불가: ${inspection.summary}`);
        }

        const norm = inspection.structure.normalizedManifest;

        return {
            schemaVersion: "2.0.0",
            packageType: norm.type,
            agent: {
                id: norm.id,
                name: norm.name,
                version: norm.version,
                description: norm.description,
                requiresConfirmation: norm.requiresConfirmation,
                permissions: norm.permissions
            },
            // 도구형 에이전트용 MCP / Tool 바인딩 메타데이터
            toolBinding: norm.type === AgentType.TOOL ? {
                entrypoint: norm.entrypoint,
                inputSchema: norm.inputSchema || { type: "string", description: "작업 지시문" },
                outputSchema: norm.outputSchema || { type: "string", description: "실행 결과" }
            } : null,
            // 에이전틱 에이전트용 LLM 주입 바인딩 메타데이터
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
