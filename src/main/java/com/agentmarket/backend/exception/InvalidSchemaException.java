// 요청 Schema 데이터를 JSON 문자열로 변환할 수 없을 때 사용하는 예외 클래스
package com.agentmarket.backend.exception;

public class InvalidSchemaException extends RuntimeException { // 잘못된 Schema 처리 원인을 보존하여 전달하는 실행 예외

    // 사용자에게 전달할 메시지와 실제 변환 실패 원인을 함께 저장
    public InvalidSchemaException(String message, Throwable cause) {
        super(message, cause);
    }
}
