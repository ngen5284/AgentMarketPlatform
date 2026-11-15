// MCP 지원 Agent 목록 조회와 관련된 HTTP 요청을 처리하는 Controller
package com.agentmarket.backend.controller;

import com.agentmarket.backend.dto.AgentSummaryResponse; // MCP 지원 Agent의 요약 정보를 반환하기 위해 사용
import com.agentmarket.backend.service.AgentService; // MCP 지원 Agent 조회 비즈니스 로직을 처리하는 Service

import org.springframework.http.ResponseEntity; // HTTP 상태 코드와 응답 데이터를 함께 반환하기 위해 사용

import org.springframework.web.bind.annotation.GetMapping; // GET 요청을 처리하는 API 메서드에 사용
import org.springframework.web.bind.annotation.RequestMapping; // Controller의 기본 URL 경로를 지정
import org.springframework.web.bind.annotation.RestController; // 해당 클래스를 REST API Controller로 지정

import java.util.List; // 여러 Agent 정보를 목록 형태로 반환하기 위해 사용

@RestController // 이 클래스를 Spring REST Controller로 등록
@RequestMapping("/api/mcp/agents") // 이 Controller의 기본 API 경로를 /api/mcp/agents로 지정
public class McpAgentController { // MCP 지원 Agent 조회 API를 처리하는 Controller 클래스

    private final AgentService agentService; // AgentService 객체를 저장하는 필드

    public McpAgentController(AgentService agentService) { // AgentService를 생성자를 통해 주입받아 필드에 저장
        this.agentService = agentService;
    }

    // API 메서드: GET /api/mcp/agents
    // MCP 사용을 지원하는 Agent 목록을 조회하는 API
    // Response: List<AgentSummaryResponse> - MCP 지원 Agent 요약 정보 목록 반환
    // HTTP 상태 코드: 200 OK
    @GetMapping
    public ResponseEntity<List<AgentSummaryResponse>> getMcpSupportedAgents() {
        return ResponseEntity.ok(agentService.getMcpSupportedAgents());
    }
}
