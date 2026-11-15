// Agent 관련 HTTP 요청을 처리하는 컨트롤러 클래스
package com.agentmarket.backend.controller;

// Controller 클래스에서 사용할 DTO와 Service를 import
// DTO: Data Transfer Object, 요청·응답 데이터 전달에 사용하는 객체
// Service: 비즈니스 로직을 처리하는 클래스

import com.agentmarket.backend.dto.AgentCreateRequest; // Agent 등록 요청을 받을 때 사용
import com.agentmarket.backend.dto.AgentResponse; // Agent 상세 조회 / 등록 / 수정 결과 반환
import com.agentmarket.backend.dto.AgentSummaryResponse; // Agent 목록 / 검색 결과 반환
import com.agentmarket.backend.dto.AgentUpdateRequest; // Agent 수정 요청을 받을 때 사용

import com.agentmarket.backend.service.AgentService; // Agent 등록, 조회, 수정, 삭제 등 실제 비즈니스 로직을 처리하는 Service 클래스

import jakarta.validation.Valid; // 요청 DTO에 설정된 유효성 검사 조건을 실행하기 위해 사용

// HTTP 응답의 상태 코드, Header, 데이터 형식, 파일 다운로드 설정에 사용
import org.springframework.http.ContentDisposition; // Content-Disposition 헤더 값을 생성하여 파일 다운로드 형식으로 설정할 때 사용
import org.springframework.http.HttpHeaders; // HTTP 응답 Header를 설정하기 위해 사용
import org.springframework.http.MediaType; // HTTP 응답 데이터의 Content-Type을 지정하기 위해 사용
import org.springframework.http.ResponseEntity; // HTTP 상태 코드, Header, 응답 데이터를 함께 반환하기 위해 사용

// Controller에서 API를 만들기 위한 핵심 어노테이션을 import
import org.springframework.web.bind.annotation.DeleteMapping; // DELETE 요청을 처리할 API 메서드에 사용
import org.springframework.web.bind.annotation.GetMapping; // GET 요청을 처리할 API 메서드에 사용
import org.springframework.web.bind.annotation.PathVariable; // URL 경로에 포함된 값을 변수로 받을 때 사용
import org.springframework.web.bind.annotation.PostMapping; // POST 요청을 처리하는 API 메서드에 사용
import org.springframework.web.bind.annotation.PutMapping; // PUT 요청을 처리하는 API 메서드에 사용
import org.springframework.web.bind.annotation.RequestBody; // HTTP 요청 본문의 JSON 데이터를 DTO 객체로 받을 때 사용
import org.springframework.web.bind.annotation.RequestMapping; // Controller 전체에 공통으로 적용할 기본 URL 경로를 지정
import org.springframework.web.bind.annotation.RequestParam; // URL의 Query Parameter 값을 받을 때 사용
import org.springframework.web.bind.annotation.RestController; // 해당 클래스를 REST API 요청을 처리하는 Controller로 지정

import java.net.URI; // 생성된 Agent의 조회 경로를 Location Header에 지정하기 위해 사용
import java.nio.charset.StandardCharsets; // agent.json 파일명을 UTF-8로 처리하기 위해 사용
import java.util.List; // 여러 Agent 정보를 목록 형태로 반환하기 위해 사용

@RestController // 해당 클래스를 REST API 요청을 처리하는 Controller로 지정
@RequestMapping("/api/agents") // 이 Controller의 모든 API에 /api/agents 기본 경로를 적용
public class AgentController { // Agent 관련 API를 처리하는 Controller 클래스

    private final AgentService agentService; // AgentService 객체를 저장하는 필드(멤버 변수)

    public AgentController(AgentService agentService) { // AgentService를 생성자를 통해 주입받아 필드에 저장
        this.agentService = agentService;
    }

    // API 메서드: GET /api/agents
    // Agent 목록 조회 및 검색 API
    // Query Parameter: keyword (선택적) - Agent 이름 또는 설명에 포함된 키워드로 검색
    // Response: List<AgentSummaryResponse> - Agent 요약 정보 목록 반환
    // HTTP 상태 코드: 200 OK
    @GetMapping
    public ResponseEntity<List<AgentSummaryResponse>> getAgents(
            @RequestParam(required = false) String keyword) {
        return ResponseEntity.ok(agentService.getAgents(keyword));
    }

    // API 메서드: GET /api/agents/{id}
    // 특정 Agent의 상세 정보를 조회하는 API
    // Path Variable: id - 조회할 Agent의 고유 ID
    // Response: AgentResponse - Agent의 상세 정보 반환
    // HTTP 상태 코드: 200 OK
    // 존재하지 않는 Agent인 경우 404 Not Found 반환
    @GetMapping("/{id}")
    public ResponseEntity<AgentResponse> getAgent(@PathVariable String id) {
        return ResponseEntity.ok(agentService.getAgent(id));
    }

    // API 메서드: POST /api/agents
    // 새로운 Agent를 등록하는 API
    // Request Body: AgentCreateRequest - 등록할 Agent 정보
    // @Valid를 통해 요청 데이터의 유효성 검사 수행
    // Response: AgentResponse - 등록된 Agent의 상세 정보 반환
    // HTTP 상태 코드: 201 Created
    // Location Header에 생성된 Agent의 조회 경로를 포함
    @PostMapping
    public ResponseEntity<AgentResponse> createAgent(
            @Valid @RequestBody AgentCreateRequest request) {

        // Service에 Agent 등록을 요청하고 등록 결과를 반환받음
        AgentResponse response = agentService.createAgent(request);

        // 201 Created 상태 코드와 생성된 Agent의 URI를 반환
        return ResponseEntity
                .created(URI.create("/api/agents/" + response.getId()))
                .body(response);
    }

    // API 메서드: PUT /api/agents/{id}
    // 기존 Agent의 정보를 수정하는 API
    // Path Variable: id - 수정할 Agent의 고유 ID
    // Request Body: AgentUpdateRequest - 수정할 Agent 정보
    // @Valid를 통해 요청 데이터의 유효성 검사 수행
    // Response: AgentResponse - 수정된 Agent의 상세 정보 반환
    // HTTP 상태 코드: 200 OK
    // Agent ID 자체는 수정하지 않음
    @PutMapping("/{id}")
    public ResponseEntity<AgentResponse> updateAgent(
            @PathVariable String id,
            @Valid @RequestBody AgentUpdateRequest request) {
        return ResponseEntity.ok(agentService.updateAgent(id, request));
    }

    // API 메서드: DELETE /api/agents/{id}
    // 특정 Agent를 삭제하는 API
    // Path Variable: id - 삭제할 Agent의 고유 ID
    // Response Body는 반환하지 않음
    // HTTP 상태 코드: 204 No Content
    @DeleteMapping("/{id}")
    public ResponseEntity<Void> deleteAgent(@PathVariable String id) {

        // Service에 해당 ID의 Agent 삭제를 요청
        agentService.deleteAgent(id);

        // 삭제 성공 시 응답 본문 없이 204 No Content 반환
        return ResponseEntity.noContent().build();
    }

    // API 메서드: GET /api/agents/{id}/download
    // 특정 Agent의 실행 정보를 agent.json 파일로 다운로드하는 API
    // Path Variable: id - 다운로드할 Agent의 고유 ID
    // Response: byte[] - JSON 파일 데이터를 바이트 배열 형태로 반환
    // HTTP 상태 코드: 200 OK
    @GetMapping("/{id}/download")
    public ResponseEntity<byte[]> downloadAgent(@PathVariable String id) {

        // Service에서 해당 Agent 정보를 agent.json 데이터로 생성
        byte[] agentJson = agentService.createAgentPackage(id);

        // 응답을 파일 다운로드 형식으로 설정하고 파일명을 agent.json으로 지정
        ContentDisposition contentDisposition = ContentDisposition.attachment()
                .filename("agent.json", StandardCharsets.UTF_8)
                .build();

        // JSON 파일 다운로드에 필요한 HTTP Header와 데이터를 반환
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON) // 응답 데이터 형식을 JSON으로 지정
                .header(HttpHeaders.CONTENT_DISPOSITION, contentDisposition.toString()) // 파일 다운로드 Header 설정
                .contentLength(agentJson.length) // 다운로드할 파일의 크기 지정
                .body(agentJson); // 실제 agent.json 데이터 반환
    }
}
