// Agent 목록, 검색 결과, MCP 지원 목록에서 요약 정보를 반환하는 DTO 클래스
package com.agentmarket.backend.dto;

import java.time.LocalDateTime; // Agent의 마지막 수정 시각을 표현하기 위해 사용

public class AgentSummaryResponse { // 목록 화면에 필요한 핵심 정보만 전달하는 응답 DTO 클래스

    private final String id; // Agent를 고유하게 구분하는 ID
    private final String agentName; // 사용자 화면에 표시할 Agent 이름
    private final String version; // Agent의 현재 버전
    private final String description; // 목록에 표시할 Agent 기능 및 용도 설명
    private final boolean browserSupport; // Browser Runtime 지원 여부
    private final boolean mcpSupport; // Local MCP 환경 지원 여부
    private final String author; // Agent 작성자 정보
    private final LocalDateTime updatedAt; // Agent 정보가 마지막으로 수정된 시각

    // 조회한 Entity의 핵심 정보로 목록용 요약 응답을 초기화
    public AgentSummaryResponse(
            String id,
            String agentName,
            String version,
            String description,
            boolean browserSupport,
            boolean mcpSupport,
            String author,
            LocalDateTime updatedAt
    ) {
        this.id = id;
        this.agentName = agentName;
        this.version = version;
        this.description = description;
        this.browserSupport = browserSupport;
        this.mcpSupport = mcpSupport;
        this.author = author;
        this.updatedAt = updatedAt;
    }

    // 각 필드의 값을 조회하며 API 응답 JSON 직렬화에도 사용되는 Getter
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

    public boolean isBrowserSupport() {
        return browserSupport;
    }

    public boolean isMcpSupport() {
        return mcpSupport;
    }

    public String getAuthor() {
        return author;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }
}
