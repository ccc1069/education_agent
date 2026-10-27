package com.edu.agent.controller;

import com.edu.agent.db.entity.User;
import com.edu.agent.db.enums.UserRole;
import com.edu.agent.db.repository.UserRepository;
import com.edu.agent.security.dto.LoginRequest;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class LearnerControllerIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    UserRepository userRepository;

    @Autowired
    PasswordEncoder passwordEncoder;

    @Autowired
    ObjectMapper objectMapper;

    private String studentToken;
    private String studentPublicId;

    @BeforeEach
    void setup() throws Exception {
        userRepository.deleteAll();

        // Register a student via /register endpoint
        mockMvc.perform(post("/api/v1/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"carol@edu.test\",\"password\":\"password123\",\"name\":\"Carol\"}"))
                .andExpect(status().isCreated());

        LoginRequest login = new LoginRequest("carol@edu.test", "password123");
        MvcResult result = mockMvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(login)))
                .andExpect(status().isOk())
                .andReturn();
        studentToken = objectMapper.readTree(result.getResponse().getContentAsString())
                .at("/data/access_token").asText();
        studentPublicId = objectMapper.readTree(result.getResponse().getContentAsString())
                .at("/data/user/learner_id").asText();
    }

    @Test
    void submit_returnsProcessedWithEvents() throws Exception {
        mockMvc.perform(post("/api/v1/submit")
                        .header("Authorization", "Bearer " + studentToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"knowledge_id\":\"arithmetic\",\"is_correct\":true,\"time_spent_seconds\":12.5}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("processed"))
                .andExpect(jsonPath("$.events_triggered").exists());
    }

    @Test
    void submit_withoutToken_returns401() throws Exception {
        mockMvc.perform(post("/api/v1/submit")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"knowledge_id\":\"arithmetic\",\"is_correct\":true}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void progress_self_returnsOk() throws Exception {
        mockMvc.perform(get("/api/v1/progress/" + studentPublicId)
                        .header("Authorization", "Bearer " + studentToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.learner_id").value(studentPublicId));
    }

    @Test
    void progress_otherStudent_forbidden() throws Exception {
        mockMvc.perform(get("/api/v1/progress/lrn_other")
                        .header("Authorization", "Bearer " + studentToken))
                .andExpect(status().isForbidden());
    }

    @Test
    void knowledgeGraph_returnsNodesAndOrder() throws Exception {
        mockMvc.perform(get("/api/v1/knowledge-graph")
                        .header("Authorization", "Bearer " + studentToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.nodes").isArray())
                .andExpect(jsonPath("$.learning_order").isArray());
    }

    @Test
    void question_andMessage_workWithAuth() throws Exception {
        mockMvc.perform(post("/api/v1/question")
                        .header("Authorization", "Bearer " + studentToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"knowledge_id\":\"fractions\",\"question\":\"什么是通分?\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("processed"));

        mockMvc.perform(post("/api/v1/message")
                        .header("Authorization", "Bearer " + studentToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"我有点累\",\"knowledge_id\":\"arithmetic\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("processed"));
    }
}
