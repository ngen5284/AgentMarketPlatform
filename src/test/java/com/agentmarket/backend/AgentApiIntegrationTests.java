package com.agentmarket.backend;

import com.agentmarket.backend.repository.AgentRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.ObjectMapper;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class AgentApiIntegrationTests {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private AgentRepository agentRepository;

    @BeforeEach
    void clearDatabase() {
        agentRepository.deleteAll();
    }

    @Test
    void createsAgent() throws Exception {
        mockMvc.perform(post("/api/agents")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json(validCreateRequest("text_analyzer", true))))
                .andExpect(status().isCreated())
                .andExpect(header().string("Location", "/api/agents/text_analyzer"))
                .andExpect(jsonPath("$.id").value("text_analyzer"))
                .andExpect(jsonPath("$.agentName").value("텍스트 분석 에이전트"))
                .andExpect(jsonPath("$.inputSchema.text").value("string"))
                .andExpect(jsonPath("$.author").value("anonymous"))
                .andExpect(jsonPath("$.createdAt").exists())
                .andExpect(jsonPath("$.updatedAt").exists());
    }

    @Test
    void returnsAgentList() throws Exception {
        createAgent("first_agent", true);
        createAgent("second_agent", true);

        mockMvc.perform(get("/api/agents"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2))
                .andExpect(jsonPath("$[0].id").exists())
                .andExpect(jsonPath("$[0].agentName").exists())
                .andExpect(jsonPath("$[0].version").exists())
                .andExpect(jsonPath("$[0].description").exists())
                .andExpect(jsonPath("$[0].browserSupport").exists())
                .andExpect(jsonPath("$[0].mcpSupport").exists())
                .andExpect(jsonPath("$[0].author").exists())
                .andExpect(jsonPath("$[0].updatedAt").exists())
                .andExpect(jsonPath("$[0].prompt").doesNotExist())
                .andExpect(jsonPath("$[0].inputSchema").doesNotExist())
                .andExpect(jsonPath("$[0].outputSchema").doesNotExist())
                .andExpect(jsonPath("$[0].requiredModel").doesNotExist())
                .andExpect(jsonPath("$[0].requiredTools").doesNotExist())
                .andExpect(jsonPath("$[0].createdAt").doesNotExist());
    }

    @Test
    void searchesByAgentNameOrDescription() throws Exception {
        Map<String, Object> first = validCreateRequest("analysis_agent", true);
        first.put("agentName", "문서 분석 도우미");
        createAgent(first);

        Map<String, Object> second = validCreateRequest("code_agent", true);
        second.put("agentName", "코드 리뷰 도우미");
        second.put("description", "Java 코드를 검토합니다.");
        createAgent(second);

        mockMvc.perform(get("/api/agents").param("keyword", "분석"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].id").value("analysis_agent"))
                .andExpect(jsonPath("$[0].prompt").doesNotExist())
                .andExpect(jsonPath("$[0].inputSchema").doesNotExist())
                .andExpect(jsonPath("$[0].outputSchema").doesNotExist());
    }

    @Test
    void returnsAgentDetail() throws Exception {
        createAgent("detail_agent", true);

        mockMvc.perform(get("/api/agents/detail_agent"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("detail_agent"))
                .andExpect(jsonPath("$.prompt").exists())
                .andExpect(jsonPath("$.inputSchema.text").value("string"))
                .andExpect(jsonPath("$.outputSchema.score").value("number"))
                .andExpect(jsonPath("$.requiredModel").value("text-generation"))
                .andExpect(jsonPath("$.requiredTools").isArray())
                .andExpect(jsonPath("$.createdAt").exists())
                .andExpect(jsonPath("$.updatedAt").exists());
    }

    @Test
    void updatesAgentWithoutChangingId() throws Exception {
        createAgent("update_agent", true);
        Map<String, Object> updateRequest = validUpdateRequest();

        mockMvc.perform(put("/api/agents/update_agent")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json(updateRequest)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("update_agent"))
                .andExpect(jsonPath("$.agentName").value("수정된 에이전트"))
                .andExpect(jsonPath("$.version").value("2.0.0"));
    }

    @Test
    void deletesAgent() throws Exception {
        createAgent("delete_agent", true);

        mockMvc.perform(delete("/api/agents/delete_agent"))
                .andExpect(status().isNoContent());

        mockMvc.perform(get("/api/agents/delete_agent"))
                .andExpect(status().isNotFound());
    }

    @Test
    void rejectsDuplicateId() throws Exception {
        createAgent("duplicate_agent", true);

        mockMvc.perform(post("/api/agents")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json(validCreateRequest("duplicate_agent", true))))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.status").value(409))
                .andExpect(jsonPath("$.path").value("/api/agents"));
    }

    @Test
    void returns404ForMissingAgent() throws Exception {
        mockMvc.perform(get("/api/agents/missing_agent"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.message", containsString("Agent를 찾을 수 없습니다.")))
                .andExpect(jsonPath("$.path").value("/api/agents/missing_agent"));
    }

    @Test
    void rejectsInvalidIdFormat() throws Exception {
        mockMvc.perform(post("/api/agents")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json(validCreateRequest("Invalid Agent", true))))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400));
    }

    @Test
    void rejectsIdLongerThan64Characters() throws Exception {
        mockMvc.perform(post("/api/agents")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json(validCreateRequest("a".repeat(65), true))))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400));
    }

    @Test
    void rejectsAgentNameLongerThan100Characters() throws Exception {
        Map<String, Object> request = validCreateRequest("long_name_agent", true);
        request.put("agentName", "가".repeat(101));

        mockMvc.perform(post("/api/agents")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400));
    }

    @Test
    void rejectsInvalidVersionFormat() throws Exception {
        Map<String, Object> request = validCreateRequest("version_agent", true);
        request.put("version", "v1");

        mockMvc.perform(post("/api/agents")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json(request)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400));
    }

    @Test
    void usesEmptyRequiredToolsWhenFieldIsMissing() throws Exception {
        mockMvc.perform(post("/api/agents")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json(validCreateRequest("no_tools_agent", false))))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.requiredTools").isArray())
                .andExpect(jsonPath("$.requiredTools").isEmpty());

        mockMvc.perform(get("/api/agents/no_tools_agent"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.requiredTools").isArray())
                .andExpect(jsonPath("$.requiredTools").isEmpty());

        mockMvc.perform(get("/api/agents/no_tools_agent/download"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.requiredTools").isArray())
                .andExpect(jsonPath("$.requiredTools").isEmpty());
    }

    @Test
    void usesEmptyRequiredToolsWhenFieldIsNull() throws Exception {
        Map<String, Object> request = validCreateRequest("null_tools_agent", true);
        request.put("requiredTools", null);

        mockMvc.perform(post("/api/agents")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.requiredTools").isArray())
                .andExpect(jsonPath("$.requiredTools").isEmpty());
    }

    @Test
    void downloadsAgentJsonPackage() throws Exception {
        createAgent("download_agent", true);

        mockMvc.perform(get("/api/agents/download_agent/download"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(header().string("Content-Disposition", containsString("agent.json")))
                .andExpect(jsonPath("$.id").value("download_agent"))
                .andExpect(jsonPath("$.author").value("anonymous"))
                .andExpect(jsonPath("$.inputSchema.text").value("string"))
                .andExpect(jsonPath("$.createdAt").doesNotExist())
                .andExpect(jsonPath("$.updatedAt").doesNotExist());
    }

    @Test
    void returnsOnlyMcpSupportedAgents() throws Exception {
        Map<String, Object> browserOnlyAgent = validCreateRequest("browser_only_agent", true);
        browserOnlyAgent.put("browserSupport", true);
        browserOnlyAgent.put("mcpSupport", false);
        createAgent(browserOnlyAgent);

        Map<String, Object> mcpAgent = validCreateRequest("mcp_agent", true);
        mcpAgent.put("browserSupport", true);
        mcpAgent.put("mcpSupport", true);
        createAgent(mcpAgent);

        mockMvc.perform(get("/api/mcp/agents"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].id").value("mcp_agent"))
                .andExpect(jsonPath("$[0].mcpSupport").value(true))
                .andExpect(jsonPath("$[0].prompt").doesNotExist())
                .andExpect(jsonPath("$[0].inputSchema").doesNotExist())
                .andExpect(jsonPath("$[0].outputSchema").doesNotExist());
    }

    private void createAgent(String id, boolean includeTools) throws Exception {
        createAgent(validCreateRequest(id, includeTools));
    }

    private void createAgent(Map<String, Object> request) throws Exception {
        mockMvc.perform(post("/api/agents")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json(request)))
                .andExpect(status().isCreated());
    }

    private Map<String, Object> validCreateRequest(String id, boolean includeTools) {
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("id", id);
        request.put("agentName", "텍스트 분석 에이전트");
        request.put("version", "1.0.0");
        request.put("description", "입력된 텍스트를 분석합니다.");
        request.put("prompt", "입력 텍스트의 핵심 내용을 분석하세요.");
        request.put("inputSchema", Map.of("text", "string", "language", "string"));
        request.put("outputSchema", Map.of("score", "number", "summary", "string"));
        request.put("requiredModel", "text-generation");
        if (includeTools) {
            request.put("requiredTools", new ArrayList<>(List.of("file_reader")));
        }
        request.put("browserSupport", true);
        request.put("mcpSupport", false);
        return request;
    }

    private Map<String, Object> validUpdateRequest() {
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("agentName", "수정된 에이전트");
        request.put("version", "2.0.0");
        request.put("description", "수정된 설명입니다.");
        request.put("prompt", "수정된 프롬프트입니다.");
        request.put("inputSchema", Map.of("content", "string"));
        request.put("outputSchema", Map.of("result", "string"));
        request.put("requiredModel", null);
        request.put("requiredTools", List.of());
        request.put("browserSupport", false);
        request.put("mcpSupport", true);
        return request;
    }

    private String json(Object value) throws Exception {
        return objectMapper.writeValueAsString(value);
    }
}
