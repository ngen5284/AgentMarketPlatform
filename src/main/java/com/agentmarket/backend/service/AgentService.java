// Agent 등록, 조회, 수정, 삭제와 Package 생성 등 핵심 비즈니스 로직을 처리하는 Service 클래스
package com.agentmarket.backend.service;

import com.agentmarket.backend.dto.AgentCreateRequest; // Agent 등록 요청 데이터를 받기 위해 사용
import com.agentmarket.backend.dto.AgentPackageResponse; // 다운로드할 agent.json 데이터 구조를 만들기 위해 사용
import com.agentmarket.backend.dto.AgentResponse; // Agent의 전체 상세 정보를 반환하기 위해 사용
import com.agentmarket.backend.dto.AgentSummaryResponse; // Agent 목록에 필요한 요약 정보를 반환하기 위해 사용
import com.agentmarket.backend.dto.AgentUpdateRequest; // Agent 수정 요청 데이터를 받기 위해 사용
import com.agentmarket.backend.entity.Agent; // 비즈니스 로직에서 DB 저장 대상 Agent를 다루기 위해 사용
import com.agentmarket.backend.exception.AgentNotFoundException; // 요청한 Agent가 없을 때 사용
import com.agentmarket.backend.exception.DuplicateAgentIdException; // 중복 ID 등록 시도를 알리기 위해 사용
import com.agentmarket.backend.exception.InvalidSchemaException; // 요청 Schema를 JSON으로 변환할 수 없을 때 사용
import com.agentmarket.backend.repository.AgentRepository; // Agent 데이터를 DB에 저장하고 조회하기 위해 사용
import org.springframework.dao.DataIntegrityViolationException; // DB 제약 조건 위반으로 발생한 중복 등록을 처리하기 위해 사용
import org.springframework.stereotype.Service; // 이 클래스를 Spring Service Bean으로 등록하기 위해 사용
import org.springframework.transaction.annotation.Transactional; // 메서드의 DB 작업 범위와 읽기 전용 여부를 지정하기 위해 사용
import tools.jackson.databind.ObjectMapper; // Schema와 Package 데이터를 JSON으로 변환하기 위해 사용

import java.util.ArrayList; // null인 Tool 목록을 안전한 빈 목록으로 변환하기 위해 사용
import java.util.List; // 여러 Agent 또는 Tool을 목록 형태로 처리하기 위해 사용
import java.util.Map; // JSON Object 형태의 Schema 데이터를 표현하기 위해 사용

@Service // Controller에서 주입받아 사용할 비즈니스 로직 Bean으로 등록
public class AgentService { // Agent 관리 기능과 Entity·DTO 변환을 담당하는 Service 클래스

    private static final String DEFAULT_AUTHOR = "anonymous"; // 별도 작성자 입력이 없는 신규 Agent에 사용할 기본 작성자명

    private final AgentRepository agentRepository; // Agent Entity의 DB 저장과 조회를 담당
    private final ObjectMapper objectMapper; // Map과 JSON 문자열, Package JSON 사이의 변환을 담당

    // DB 접근 객체와 JSON 변환 객체를 생성자를 통해 주입받아 필드에 저장
    public AgentService(AgentRepository agentRepository, ObjectMapper objectMapper) {
        this.agentRepository = agentRepository;
        this.objectMapper = objectMapper;
    }

    // 새로운 Agent를 등록한다.
    // 등록 전 동일한 ID가 존재하는지 검사하고 요청 DTO를 Entity로 옮겨 DB에 저장한다.
    @Transactional
    public AgentResponse createAgent(AgentCreateRequest request) {
        // 애플리케이션 단계에서 동일 ID가 이미 등록되어 있는지 먼저 확인
        if (agentRepository.existsById(request.getId())) {
            throw new DuplicateAgentIdException(request.getId());
        }

        // 등록 요청의 고유 ID로 Entity를 만들고 나머지 요청 값을 적용
        Agent agent = new Agent(request.getId());
        applyCreateRequest(agent, request);

        try {
            // Entity를 저장하고 변경 내용을 즉시 flush하여 DB에 반영한 뒤 상세 응답으로 변환
            Agent savedAgent = agentRepository.saveAndFlush(agent);
            return toResponse(savedAgent);
        } catch (DataIntegrityViolationException exception) {
            // 동시에 같은 ID가 등록되는 경우에도 409로 처리한다.
            throw new DuplicateAgentIdException(request.getId());
        }
    }

    // keyword가 없으면 전체 Agent를 조회하고, 있으면 이름 또는 설명에서 검색한다.
    // 조회된 Entity 목록은 화면에 필요한 요약 응답 목록으로 변환한다.
    @Transactional(readOnly = true)
    public List<AgentSummaryResponse> getAgents(String keyword) {
        List<Agent> agents;
        // null, 빈 문자열, 공백만 입력된 경우 검색 조건 없이 전체 목록 조회
        if (keyword == null || keyword.isBlank()) {
            agents = agentRepository.findAll();
        } else {
            // 검색어 앞뒤 공백을 제거한 뒤 Repository의 keyword 검색 실행
            String trimmedKeyword = keyword.trim();
            agents = agentRepository.searchByKeyword(trimmedKeyword);
        }

        // 각 Entity를 목록용 요약 DTO로 변환
        return agents.stream()
                .map(this::toSummaryResponse)
                .toList();
    }

    // 고유 ID로 Agent를 조회하고 전체 상세 응답으로 변환한다.
    // 존재하지 않으면 findAgent에서 AgentNotFoundException이 발생한다.
    @Transactional(readOnly = true)
    public AgentResponse getAgent(String id) {
        return toResponse(findAgent(id));
    }

    // MCP 사용을 지원하는 Agent만 조회하여 요약 응답 목록으로 변환한다.
    @Transactional(readOnly = true)
    public List<AgentSummaryResponse> getMcpSupportedAgents() {
        return agentRepository.findByMcpSupportTrue().stream()
                .map(this::toSummaryResponse)
                .toList();
    }

    // 기존 Agent를 조회한 뒤 수정 요청의 값으로 변경하여 DB에 반영한다.
    // URL로 받은 고유 ID는 변경하지 않고 나머지 관리 정보만 수정한다.
    @Transactional
    public AgentResponse updateAgent(String id, AgentUpdateRequest request) {
        Agent agent = findAgent(id);
        // 수정 DTO의 값을 Entity에 적용하고 Schema Map은 DB 저장용 JSON 문자열로 변환
        agent.setAgentName(request.getAgentName());
        agent.setVersion(request.getVersion());
        agent.setDescription(request.getDescription());
        agent.setPrompt(request.getPrompt());
        agent.setInputSchema(toJson(request.getInputSchema()));
        agent.setOutputSchema(toJson(request.getOutputSchema()));
        agent.setRequiredModel(request.getRequiredModel());
        agent.setRequiredTools(emptyIfNull(request.getRequiredTools()));
        agent.setBrowserSupport(request.getBrowserSupport());
        agent.setMcpSupport(request.getMcpSupport());

        // 변경 내용을 즉시 flush하여 DB에 SQL 반영을 수행한 뒤 상세 응답으로 변환
        Agent updatedAgent = agentRepository.saveAndFlush(agent);
        return toResponse(updatedAgent);
    }

    // 고유 ID로 Agent를 확인한 뒤 DB에서 삭제한다.
    @Transactional
    public void deleteAgent(String id) {
        Agent agent = findAgent(id);
        agentRepository.delete(agent);
    }

    // Agent 전체 정보를 다운로드 가능한 agent.json 바이트 데이터로 생성한다.
    // DB에 문자열로 저장된 Schema는 다시 Map으로 변환하여 JSON Object로 포함한다.
    @Transactional(readOnly = true)
    public byte[] createAgentPackage(String id) {
        Agent agent = findAgent(id);
        // Entity의 실행 정보를 다운로드 전용 Package DTO로 구성
        AgentPackageResponse packageResponse = new AgentPackageResponse(
                agent.getId(),
                agent.getAgentName(),
                agent.getVersion(),
                agent.getDescription(),
                agent.getPrompt(),
                fromJson(agent.getInputSchema()),
                fromJson(agent.getOutputSchema()),
                agent.getRequiredModel(),
                List.copyOf(agent.getRequiredTools()),
                agent.isBrowserSupport(),
                agent.isMcpSupport(),
                agent.getAuthor()
        );

        try {
            // 읽기 쉬운 들여쓰기를 적용한 agent.json 바이트 배열 생성
            return objectMapper.writerWithDefaultPrettyPrinter().writeValueAsBytes(packageResponse);
        } catch (Exception exception) {
            throw new IllegalStateException("Agent Package JSON 생성에 실패했습니다.", exception);
        }
    }

    // 공통 ID 조회를 수행하고 Agent가 없으면 404 처리에 사용할 예외를 발생시킨다.
    private Agent findAgent(String id) {
        return agentRepository.findById(id)
                .orElseThrow(() -> new AgentNotFoundException(id));
    }

    // 등록 요청 DTO의 값을 새 Entity에 옮기고 Schema는 DB 저장용 JSON 문자열로 변환한다.
    // 작성자 입력 필드가 없으므로 기본 작성자명을 설정한다.
    private void applyCreateRequest(Agent agent, AgentCreateRequest request) {
        agent.setAgentName(request.getAgentName());
        agent.setVersion(request.getVersion());
        agent.setDescription(request.getDescription());
        agent.setPrompt(request.getPrompt());
        agent.setInputSchema(toJson(request.getInputSchema()));
        agent.setOutputSchema(toJson(request.getOutputSchema()));
        agent.setRequiredModel(request.getRequiredModel());
        agent.setRequiredTools(emptyIfNull(request.getRequiredTools()));
        agent.setBrowserSupport(request.getBrowserSupport());
        agent.setMcpSupport(request.getMcpSupport());
        agent.setAuthor(DEFAULT_AUTHOR);
    }

    // Agent Entity의 모든 필드를 상세 조회용 DTO로 변환한다.
    // DB에 문자열로 저장된 Schema JSON은 API 응답용 Map으로 복원한다.
    private AgentResponse toResponse(Agent agent) {
        return new AgentResponse(
                agent.getId(),
                agent.getAgentName(),
                agent.getVersion(),
                agent.getDescription(),
                agent.getPrompt(),
                fromJson(agent.getInputSchema()),
                fromJson(agent.getOutputSchema()),
                agent.getRequiredModel(),
                List.copyOf(agent.getRequiredTools()),
                agent.isBrowserSupport(),
                agent.isMcpSupport(),
                agent.getAuthor(),
                agent.getCreatedAt(),
                agent.getUpdatedAt()
        );
    }

    // 목록과 검색 결과에 필요한 핵심 필드만 요약 응답 DTO로 변환한다.
    private AgentSummaryResponse toSummaryResponse(Agent agent) {
        return new AgentSummaryResponse(
                agent.getId(),
                agent.getAgentName(),
                agent.getVersion(),
                agent.getDescription(),
                agent.isBrowserSupport(),
                agent.isMcpSupport(),
                agent.getAuthor(),
                agent.getUpdatedAt()
        );
    }

    // Tool 목록이 null이면 빈 목록을 반환하고, 값이 있으면 복사본을 만들어 반환한다.
    private List<String> emptyIfNull(List<String> requiredTools) {
        return requiredTools == null ? new ArrayList<>() : new ArrayList<>(requiredTools);
    }

    // 요청 DTO의 Schema Map을 DB에 저장할 JSON 문자열로 변환한다.
    // 직렬화할 수 없는 값이 포함되면 InvalidSchemaException으로 변환한다.
    private String toJson(Map<String, Object> schema) {
        try {
            return objectMapper.writeValueAsString(schema);
        } catch (Exception exception) {
            throw new InvalidSchemaException("Schema를 JSON으로 변환할 수 없습니다.", exception);
        }
    }

    // DB에 문자열로 저장된 Schema JSON을 API 응답용 Map으로 변환한다.
    @SuppressWarnings("unchecked")
    private Map<String, Object> fromJson(String schemaJson) {
        try {
            return objectMapper.readValue(schemaJson, Map.class);
        } catch (Exception exception) {
            throw new IllegalStateException("저장된 Schema JSON을 읽을 수 없습니다.", exception);
        }
    }
}
