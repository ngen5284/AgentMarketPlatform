// 이미 존재하는 Agent ID로 새 Agent 등록을 시도했을 때 사용하는 예외 클래스
package com.agentmarket.backend.exception;

public class DuplicateAgentIdException extends RuntimeException { // Agent ID 중복 상황을 Service에서 알리기 위한 실행 예외

    // 중복된 Agent ID를 포함한 오류 메시지로 예외를 생성
    public DuplicateAgentIdException(String id) {
        super("이미 등록된 Agent ID입니다. id=" + id);
    }
}
