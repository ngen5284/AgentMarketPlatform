// 다운로드용 agent.json Package의 데이터 구조를 표현하는 DTO 클래스
package com.agentmarket.backend.dto;

import java.util.List; // Agent 실행에 필요한 여러 Tool 이름을 목록으로 포함하기 위해 사용
import java.util.Map; // 입력·출력 Schema를 JSON Object 형태로 포함하기 위해 사용

public class AgentPackageResponse { // Agent Package 파일로 직렬화할 정보를 저장하는 DTO 클래스

    private final String id; // Package에 포함할 Agent 고유 ID
    private final String agentName; // Package에 포함할 Agent 이름
    private final String version; // Package에 포함할 Agent 버전
    private final String description; // Agent의 기능과 용도 설명
    private final String prompt; // Agent 실행 시 모델에 전달할 Prompt
    private final Map<String, Object> inputSchema; // Agent가 받을 입력 데이터의 구조
    private final Map<String, Object> outputSchema; // Agent가 반환할 출력 데이터의 구조
    private final String requiredModel; // Agent 실행에 필요한 모델 조건
    private final List<String> requiredTools; // Agent 실행에 필요한 Tool 이름 목록
    private final boolean browserSupport; // Browser Runtime 지원 여부
    private final boolean mcpSupport; // Local MCP 환경 지원 여부
    private final String author; // Agent 작성자 정보

    // DB에서 조회한 Agent 정보로 다운로드용 Package 데이터를 초기화
    public AgentPackageResponse(
            String id,
            String agentName,
            String version,
            String description,
            String prompt,
            Map<String, Object> inputSchema,
            Map<String, Object> outputSchema,
            String requiredModel,
            List<String> requiredTools,
            boolean browserSupport,
            boolean mcpSupport,
            String author
    ) {
        this.id = id;
        this.agentName = agentName;
        this.version = version;
        this.description = description;
        this.prompt = prompt;
        this.inputSchema = inputSchema;
        this.outputSchema = outputSchema;
        this.requiredModel = requiredModel;
        this.requiredTools = requiredTools;
        this.browserSupport = browserSupport;
        this.mcpSupport = mcpSupport;
        this.author = author;
    }

    // 각 필드의 값을 조회하며 agent.json 직렬화에도 사용되는 Getter
    public String getId() {
        return id;
    }

    public String getAgentName() {
        return agentName;
    }

    public String getVersion() {
        return version;
    }

    public String getDescription() {
        return description;
    }

    public String getPrompt() {
        return prompt;
    }

    public Map<String, Object> getInputSchema() {
        return inputSchema;
    }

    public Map<String, Object> getOutputSchema() {
        return outputSchema;
    }

    public String getRequiredModel() {
        return requiredModel;
    }

    public List<String> getRequiredTools() {
        return requiredTools;
    }

    public boolean isBrowserSupport() {
        return browserSupport;
    }

    public boolean isMcpSupport() {
        return mcpSupport;
    }

    public String getAuthor() {
        return author;
    }
}
