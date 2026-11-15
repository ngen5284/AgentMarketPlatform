// 기존 Agent 수정 요청 데이터를 전달받는 DTO 클래스
package com.agentmarket.backend.dto;

import jakarta.validation.constraints.NotBlank; // 문자열이 null, 빈 문자열 또는 공백만 있는 값인지 검사
import jakarta.validation.constraints.NotNull; // 요청 값이 null인지 검사
import jakarta.validation.constraints.Pattern; // 문자열이 지정된 정규식 형식을 만족하는지 검사
import jakarta.validation.constraints.Size; // 문자열 또는 컬렉션의 최대 크기를 제한

import java.util.List; // Agent 실행에 필요한 여러 Tool 이름을 목록으로 전달하기 위해 사용
import java.util.Map; // JSON Object 형태의 Schema를 Java 객체로 전달하기 위해 사용

public class AgentUpdateRequest { // 기존 Agent의 변경할 정보를 저장하는 DTO 클래스

    // 수정할 Agent 이름
    // 필수 입력이며 최대 100자까지 허용
    @NotBlank(message = "agentName은 필수입니다.")
    @Size(max = 100, message = "agentName은 최대 100자까지 입력할 수 있습니다.")
    private String agentName;

    // 수정할 Agent 버전
    // 필수 입력이며 최대 30자, 1.0.0과 같은 숫자 3단계 형식만 허용
    @NotBlank(message = "version은 필수입니다.")
    @Size(max = 30, message = "version은 최대 30자까지 입력할 수 있습니다.")
    @Pattern(regexp = "^\\d+\\.\\d+\\.\\d+$", message = "version은 1.0.0과 같은 숫자 3단계 형식이어야 합니다.")
    private String version;

    // 수정할 Agent의 기능 및 용도 설명
    // 필수 입력이며 최대 2000자까지 허용
    @NotBlank(message = "description은 필수입니다.")
    @Size(max = 2000, message = "description은 최대 2000자까지 입력할 수 있습니다.")
    private String description;

    // 수정할 Agent 실행 Prompt
    // 필수 입력이며 최대 10000자까지 허용
    @NotBlank(message = "prompt는 필수입니다.")
    @Size(max = 10000, message = "prompt는 최대 10000자까지 입력할 수 있습니다.")
    private String prompt;

    // 수정할 입력 데이터 구조이며 반드시 전달해야 함
    @NotNull(message = "inputSchema는 필수입니다.")
    private Map<String, Object> inputSchema;

    // 수정할 출력 데이터 구조이며 반드시 전달해야 함
    @NotNull(message = "outputSchema는 필수입니다.")
    private Map<String, Object> outputSchema;

    private String requiredModel; // Agent 실행에 필요한 모델 조건

    private List<String> requiredTools; // Agent 실행에 필요한 Tool 이름 목록

    // Browser Runtime 지원 여부이며 null은 허용하지 않음
    @NotNull(message = "browserSupport는 필수입니다.")
    private Boolean browserSupport;

    // Local MCP 환경 지원 여부이며 null은 허용하지 않음
    @NotNull(message = "mcpSupport는 필수입니다.")
    private Boolean mcpSupport;

    // 요청 JSON을 Java 객체로 변환할 때 사용할 기본 생성자
    public AgentUpdateRequest() {
    }

    // 각 필드의 값을 조회하고 설정하기 위한 Getter / Setter
    public String getAgentName() {
        return agentName;
    }

    public void setAgentName(String agentName) {
        this.agentName = agentName;
    }

    public String getVersion() {
        return version;
    }

    public void setVersion(String version) {
        this.version = version;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public String getPrompt() {
        return prompt;
    }

    public void setPrompt(String prompt) {
        this.prompt = prompt;
    }

    public Map<String, Object> getInputSchema() {
        return inputSchema;
    }

    public void setInputSchema(Map<String, Object> inputSchema) {
        this.inputSchema = inputSchema;
    }

    public Map<String, Object> getOutputSchema() {
        return outputSchema;
    }

    public void setOutputSchema(Map<String, Object> outputSchema) {
        this.outputSchema = outputSchema;
    }

    public String getRequiredModel() {
        return requiredModel;
    }

    public void setRequiredModel(String requiredModel) {
        this.requiredModel = requiredModel;
    }

    public List<String> getRequiredTools() {
        return requiredTools;
    }

    public void setRequiredTools(List<String> requiredTools) {
        this.requiredTools = requiredTools;
    }

    public Boolean getBrowserSupport() {
        return browserSupport;
    }

    public void setBrowserSupport(Boolean browserSupport) {
        this.browserSupport = browserSupport;
    }

    public Boolean getMcpSupport() {
        return mcpSupport;
    }

    public void setMcpSupport(Boolean mcpSupport) {
        this.mcpSupport = mcpSupport;
    }
}
