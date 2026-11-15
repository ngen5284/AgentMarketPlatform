// 애플리케이션에서 발생한 예외를 일관된 HTTP 오류 응답으로 변환하는 전역 예외 처리 클래스
package com.agentmarket.backend.exception;

import jakarta.servlet.http.HttpServletRequest; // 오류가 발생한 요청 URI를 확인하기 위해 사용
import org.slf4j.Logger; // 예상하지 못한 서버 오류의 상세 내용을 로그로 기록하기 위해 사용
import org.slf4j.LoggerFactory; // 현재 클래스에서 사용할 Logger를 생성하기 위해 사용
import org.springframework.http.HttpStatus; // 예외 상황에 맞는 HTTP 상태 코드를 지정하기 위해 사용
import org.springframework.http.ResponseEntity; // 상태 코드와 오류 응답 데이터를 함께 반환하기 위해 사용
import org.springframework.http.converter.HttpMessageNotReadableException; // 읽을 수 없는 요청 JSON을 처리하기 위해 사용
import org.springframework.validation.FieldError; // DTO 유효성 검사에서 실패한 필드 정보를 확인하기 위해 사용
import org.springframework.web.bind.MethodArgumentNotValidException; // @Valid 검사 실패 예외를 처리하기 위해 사용
import org.springframework.web.bind.annotation.ExceptionHandler; // 예외별 처리 메서드를 지정하기 위해 사용
import org.springframework.web.bind.annotation.RestControllerAdvice; // 모든 REST Controller에 공통 예외 처리를 적용하기 위해 사용

@RestControllerAdvice // REST API 전역에서 발생하는 예외를 이 클래스가 처리하도록 등록
public class GlobalExceptionHandler { // 예외를 HTTP 상태 코드와 ErrorResponse로 변환하는 클래스

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class); // 서버 내부 오류 기록에 사용할 Logger

    // 존재하지 않는 Agent 요청을 404 Not Found 응답으로 변환
    @ExceptionHandler(AgentNotFoundException.class)
    public ResponseEntity<ErrorResponse> handleAgentNotFound(
            AgentNotFoundException exception,
            HttpServletRequest request
    ) {
        return createErrorResponse(HttpStatus.NOT_FOUND, exception.getMessage(), request);
    }

    // 이미 등록된 Agent ID 사용을 409 Conflict 응답으로 변환
    @ExceptionHandler(DuplicateAgentIdException.class)
    public ResponseEntity<ErrorResponse> handleDuplicateAgentId(
            DuplicateAgentIdException exception,
            HttpServletRequest request
    ) {
        return createErrorResponse(HttpStatus.CONFLICT, exception.getMessage(), request);
    }

    // 요청 DTO의 Validation 실패를 400 Bad Request 응답으로 변환
    // 여러 검증 오류 중 첫 번째 메시지를 클라이언트에 전달
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleValidation(
            MethodArgumentNotValidException exception,
            HttpServletRequest request
    ) {
        FieldError firstError = exception.getBindingResult().getFieldErrors().stream()
                .findFirst()
                .orElse(null);
        String message = firstError == null ? "입력값이 올바르지 않습니다." : firstError.getDefaultMessage();
        return createErrorResponse(HttpStatus.BAD_REQUEST, message, request);
    }

    // JSON 문법 오류나 요청 타입 불일치를 400 Bad Request 응답으로 변환
    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ErrorResponse> handleUnreadableMessage(
            HttpMessageNotReadableException exception,
            HttpServletRequest request
    ) {
        return createErrorResponse(HttpStatus.BAD_REQUEST, "요청 JSON 형식이 올바르지 않습니다.", request);
    }

    // Schema JSON 변환 실패를 400 Bad Request 응답으로 변환
    @ExceptionHandler(InvalidSchemaException.class)
    public ResponseEntity<ErrorResponse> handleInvalidSchema(
            InvalidSchemaException exception,
            HttpServletRequest request
    ) {
        return createErrorResponse(HttpStatus.BAD_REQUEST, exception.getMessage(), request);
    }

    // 별도로 처리하지 않은 예외를 로그에 기록하고 500 Internal Server Error로 변환
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleUnexpected(
            Exception exception,
            HttpServletRequest request
    ) {
        log.error("예상하지 못한 API 오류가 발생했습니다. path={}", request.getRequestURI(), exception);
        return createErrorResponse(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "서버 내부 오류가 발생했습니다.",
                request
        );
    }

    // 예외별 상태 코드와 메시지, 요청 경로를 공통 ErrorResponse 형태로 생성
    private ResponseEntity<ErrorResponse> createErrorResponse(
            HttpStatus status,
            String message,
            HttpServletRequest request
    ) {
        ErrorResponse response = new ErrorResponse(status.value(), message, request.getRequestURI());
        return ResponseEntity.status(status).body(response);
    }
}
