// Agent 데이터의 DB 저장 및 조회를 담당하는 Repository
package com.agentmarket.backend.repository;

import com.agentmarket.backend.entity.Agent; // DB 접근 대상으로 사용할 Agent Entity
import org.springframework.data.jpa.repository.JpaRepository; // 기본 CRUD와 페이징 기능을 제공받기 위해 사용
import org.springframework.data.jpa.repository.Query; // Agent 검색 조건을 JPQL로 직접 정의하기 위해 사용
import org.springframework.data.repository.query.Param; // JPQL의 keyword 이름과 메서드 인자를 연결하기 위해 사용

import java.util.List; // 조회된 여러 Agent를 목록 형태로 반환하기 위해 사용

public interface AgentRepository extends JpaRepository<Agent, String> { // Agent Entity를 관리하며 String 타입 id를 Primary Key로 사용하는 Repository

    // Agent 이름 또는 설명에 keyword가 포함된 Agent를 대소문자 구분 없이 검색
    @Query("""
            SELECT agent
            FROM Agent agent
            WHERE LOWER(agent.agentName) LIKE LOWER(CONCAT('%', :keyword, '%'))
               OR LOWER(agent.description) LIKE LOWER(CONCAT('%', :keyword, '%'))
            """)
    List<Agent> searchByKeyword(@Param("keyword") String keyword);

    // 메서드 이름을 기반으로 MCP 사용을 지원하는 Agent만 조회
    List<Agent> findByMcpSupportTrue();
}
