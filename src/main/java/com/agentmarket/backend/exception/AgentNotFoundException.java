// 요청한 Agent ID가 DB에 존재하지 않을 때 사용하는 예외 클래스
package com.agentmarket.backend.exception;

public class AgentNotFoundException extends RuntimeException { // 존재하지 않는 Agent 요청을 Service에서 알리기 위한 실행 예외

    // 찾지 못한 Agent ID를 포함한 오류 메시지로 예외를 생성
    public AgentNotFoundException(String id) {
        super("Agent를 찾을 수 없습니다. id=" + id);
    }
}
