// Agent 정보를 데이터베이스에 저장하기 위한 JPA Entity 클래스
package com.agentmarket.backend.entity;

import jakarta.persistence.CollectionTable; // Tool 목록을 저장할 별도 컬렉션 테이블을 지정하기 위해 사용
import jakarta.persistence.Column; // 필드와 DB 컬럼의 이름, 길이, 필수 여부 등을 설정하기 위해 사용
import jakarta.persistence.ElementCollection; // 문자열 Tool 목록을 Entity와 함께 DB에 저장하기 위해 사용
import jakarta.persistence.Entity; // 이 클래스를 JPA가 관리하는 DB Entity로 지정하기 위해 사용
import jakarta.persistence.FetchType; // Tool 목록을 실제 사용 시점에 조회하도록 설정하기 위해 사용
import jakarta.persistence.Id; // Agent의 Primary Key 필드를 지정하기 위해 사용
import jakarta.persistence.JoinColumn; // Tool 컬렉션 테이블이 Agent를 참조할 외래 키 컬럼을 지정하기 위해 사용
import jakarta.persistence.OrderColumn; // Tool 목록의 저장 순서를 유지할 컬럼을 지정하기 위해 사용
import jakarta.persistence.PrePersist; // Entity가 처음 저장되기 직전에 실행할 메서드를 지정하기 위해 사용
import jakarta.persistence.PreUpdate; // Entity가 수정되기 직전에 실행할 메서드를 지정하기 위해 사용
import jakarta.persistence.Table; // Entity와 연결할 DB 테이블 이름을 지정하기 위해 사용

import java.time.LocalDateTime; // Agent의 생성 시각과 마지막 수정 시각을 저장하기 위해 사용
import java.util.ArrayList; // Tool 목록을 비어 있는 변경 가능한 목록으로 초기화하기 위해 사용
import java.util.List; // Agent 실행에 필요한 여러 Tool 이름을 순서대로 관리하기 위해 사용

@Entity // 이 클래스를 JPA가 관리하고 DB에 저장할 Entity로 지정
@Table(name = "agents") // Agent 정보를 저장하는 agents 테이블과 연결
public class Agent { // Agent의 전체 정보를 DB 테이블과 연결하여 관리하는 Entity 클래스

    // Agent를 고유하게 구분하는 Primary Key
    // 서버에서 자동 생성하지 않고 등록자가 직접 입력하며 등록 후 변경하지 않음
    @Id
    @Column(length = 100, nullable = false, updatable = false)
    private String id;

    // 사용자 화면에 표시할 Agent 이름을 agent_name 컬럼에 저장
    @Column(name = "agent_name", nullable = false, length = 200)
    private String agentName;

    // Agent의 현재 버전을 필수 값으로 저장
    @Column(nullable = false, length = 50)
    private String version;

    // Agent의 기능과 용도 설명을 길이 제한이 큰 TEXT 컬럼에 저장
    @Column(nullable = false, columnDefinition = "TEXT")
    private String description;

    // Agent 실행 시 모델에 전달할 Prompt를 TEXT 컬럼에 저장
    @Column(nullable = false, columnDefinition = "TEXT")
    private String prompt;

    // Agent가 받을 입력 구조를 JSON 문자열로 변환하여 input_schema 컬럼에 저장
    @Column(name = "input_schema", nullable = false, columnDefinition = "TEXT")
    private String inputSchema;

    // Agent가 반환할 출력 구조를 JSON 문자열로 변환하여 output_schema 컬럼에 저장
    @Column(name = "output_schema", nullable = false, columnDefinition = "TEXT")
    private String outputSchema;

    // Agent 실행에 필요한 모델 조건을 저장하며 값이 없을 수도 있음
    @Column(name = "required_model", length = 200)
    private String requiredModel;

    // Agent 실행에 필요한 Tool 이름을 agent_required_tools 컬렉션 테이블에 저장
    // agent_id로 원본 Agent와 연결하고 tool_order로 입력된 Tool 순서를 유지
    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
            name = "agent_required_tools",
            joinColumns = @JoinColumn(name = "agent_id")
    )
    @OrderColumn(name = "tool_order")
    @Column(name = "tool_name", nullable = false, length = 200)
    private List<String> requiredTools = new ArrayList<>();

    // Browser Runtime을 지원하는지 여부를 저장
    @Column(name = "browser_support", nullable = false)
    private boolean browserSupport;

    // Local MCP 환경을 지원하는지 여부를 저장
    @Column(name = "mcp_support", nullable = false)
    private boolean mcpSupport;

    // Agent를 등록한 작성자 정보를 저장
    @Column(nullable = false, length = 100)
    private String author;

    // Agent가 처음 DB에 저장된 시각이며 이후에는 변경하지 않음
    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    // Agent 정보가 마지막으로 수정된 시각
    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    // JPA가 DB 조회 결과를 Entity로 생성할 때 사용하는 기본 생성자
    protected Agent() {
    }

    // 등록자가 입력한 고유 ID로 새로운 Agent Entity를 생성
    public Agent(String id) {
        this.id = id;
    }

    // Entity가 처음 저장되기 직전에 생성·수정 시각을 현재 시각으로 설정
    // Tool 목록이 null이면 빈 목록으로 바꾸어 컬렉션 저장 과정의 오류를 방지
    @PrePersist
    protected void onCreate() {
        LocalDateTime now = LocalDateTime.now();
        this.createdAt = now;
        this.updatedAt = now;
        if (this.requiredTools == null) {
            this.requiredTools = new ArrayList<>();
        }
    }

    // 기존 Entity가 수정되기 직전에 마지막 수정 시각을 현재 시각으로 갱신
    @PreUpdate
    protected void onUpdate() {
        this.updatedAt = LocalDateTime.now();
    }

    // 각 필드의 값을 조회하고 변경하기 위한 Getter / Setter
    // 고유 ID와 생성·수정 시각은 외부에서 임의로 바꾸지 않도록 Setter를 제공하지 않음
    public String getId() {
        return id;
    }

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

    public String getInputSchema() {
        return inputSchema;
    }

    public void setInputSchema(String inputSchema) {
        this.inputSchema = inputSchema;
    }

    public String getOutputSchema() {
        return outputSchema;
    }

    public void setOutputSchema(String outputSchema) {
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
        this.requiredTools = requiredTools == null ? new ArrayList<>() : new ArrayList<>(requiredTools);
    }

    public boolean isBrowserSupport() {
        return browserSupport;
    }

    public void setBrowserSupport(boolean browserSupport) {
        this.browserSupport = browserSupport;
    }

    public boolean isMcpSupport() {
        return mcpSupport;
    }

    public void setMcpSupport(boolean mcpSupport) {
        this.mcpSupport = mcpSupport;
    }

    public String getAuthor() {
        return author;
    }

    public void setAuthor(String author) {
        this.author = author;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }
}
