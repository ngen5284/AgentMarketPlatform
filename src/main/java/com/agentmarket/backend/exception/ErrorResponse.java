// API 처리 중 발생한 오류 정보를 클라이언트에 반환하는 응답 DTO 클래스
package com.agentmarket.backend.exception;

public class ErrorResponse { // 모든 예외 응답에서 공통으로 사용할 오류 데이터 구조

    private final int status; // 클라이언트에 반환할 HTTP 상태 코드
    private final String message; // 오류가 발생한 이유를 설명하는 메시지
    private final String path; // 오류가 발생한 요청 URI

    // HTTP 상태 코드, 오류 메시지, 요청 경로로 오류 응답을 초기화
    public ErrorResponse(int status, String message, String path) {
        this.status = status;
        this.message = message;
        this.path = path;
    }

    // 각 오류 정보를 조회하며 오류 응답 JSON 직렬화에도 사용되는 Getter
    public int getStatus() {
        return status;
    }

    public String getMessage() {
        return message;
    }

    public String getPath() {
        return path;
    }
}
