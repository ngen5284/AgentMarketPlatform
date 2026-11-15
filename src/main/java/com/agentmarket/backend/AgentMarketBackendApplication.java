// AI Agent Marketplace Backend Spring Boot 애플리케이션의 실행 시작점
package com.agentmarket.backend;

import org.springframework.boot.SpringApplication; // Spring Boot 애플리케이션을 시작하기 위해 사용
import org.springframework.boot.autoconfigure.SpringBootApplication; // 자동 설정과 컴포넌트 탐색을 활성화하기 위해 사용

@SpringBootApplication // Spring Boot 설정 클래스이자 컴포넌트 탐색의 기준점으로 지정
public class AgentMarketBackendApplication { // 백엔드 애플리케이션을 실행하는 메인 클래스

    // Spring Boot 애플리케이션을 실행
    public static void main(String[] args) {
        SpringApplication.run(AgentMarketBackendApplication.class, args);
    }
}
