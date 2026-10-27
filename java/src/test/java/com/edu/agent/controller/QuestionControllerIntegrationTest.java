package com.edu.agent.controller;

import com.edu.agent.db.entity.User;
import com.edu.agent.db.enums.UserRole;
import com.edu.agent.db.repository.QuestionRepository;
import com.edu.agent.db.repository.UserRepository;
import com.edu.agent.security.dto.LoginRequest;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.math.BigInteger;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class QuestionControllerIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    QuestionRepository questionRepository;

    @Autowired
    UserRepository userRepository;

    @Autowired
    ObjectMapper objectMapper;

    private String teacherToken;
    private String studentToken;
    private BigInteger publishedQuestionId;
    private BigInteger draftQuestionId;

    @BeforeEach
    void setup() throws Exception {
        questionRepository.deleteAll();
        userRepository.deleteAll();
        registerAndPromote("teacher-q@edu.test", UserRole.TEACHER);
        registerStudent("student-q@edu.test");
        teacherToken = login("teacher-q@edu.test");
        studentToken = login("student-q@edu.test");

        MvcResult genResult = mockMvc.perform(post("/api/v1/questions/generate")
                        .header("Authorization", "Bearer " + teacherToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"knowledge_id\":\"arithmetic\",\"question_type\":\"multiple_choice\",\"difficulty\":2}"))
                .andExpect(status().isCreated())
                .andReturn();
        draftQuestionId = BigInteger.valueOf(objectMapper.readTree(genResult.getResponse().getContentAsString())
                .at("/data/id").asLong());

        MvcResult gen2 = mockMvc.perform(post("/api/v1/questions/generate")
                        .header("Authorization", "Bearer " + teacherToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"knowledge_id\":\"fractions\",\"difficulty\":3}"))
                .andExpect(status().isCreated())
                .andReturn();
        BigInteger toPublish = BigInteger.valueOf(objectMapper.readTree(gen2.getResponse().getContentAsString())
                .at("/data/id").asLong());

        mockMvc.perform(post("/api/v1/questions/" + toPublish + "/status")
                        .header("Authorization", "Bearer " + teacherToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"new_status\":\"review\"}"))
                .andExpect(status().isOk());
        mockMvc.perform(post("/api/v1/questions/" + toPublish + "/status")
                        .header("Authorization", "Bearer " + teacherToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"new_status\":\"published\"}"))
                .andExpect(status().isOk());
        publishedQuestionId = toPublish;
    }

    @Test
    void studentCannotGenerate() throws Exception {
        mockMvc.perform(post("/api/v1/questions/generate")
                        .header("Authorization", "Bearer " + studentToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"knowledge_id\":\"arithmetic\",\"difficulty\":2}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void studentCannotSeeAnswer() throws Exception {
        mockMvc.perform(get("/api/v1/questions/" + publishedQuestionId)
                        .header("Authorization", "Bearer " + studentToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.answer").isEmpty());
    }

    @Test
    void studentCannotAccessDraft() throws Exception {
        mockMvc.perform(get("/api/v1/questions/" + draftQuestionId)
                        .header("Authorization", "Bearer " + studentToken))
                .andExpect(status().isForbidden());
    }

    @Test
    void teacherSeesAnswer() throws Exception {
        mockMvc.perform(get("/api/v1/questions/" + publishedQuestionId)
                        .header("Authorization", "Bearer " + teacherToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.answer").value("示例答案"));
    }

    @Test
    void checkAnswer_returnsCorrectness() throws Exception {
        mockMvc.perform(post("/api/v1/questions/" + publishedQuestionId + "/check")
                        .header("Authorization", "Bearer " + studentToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"student_answer\":\"示例答案\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.is_correct").value(true));
    }

    @Test
    void invalidTransition_rejected() throws Exception {
        mockMvc.perform(post("/api/v1/questions/" + draftQuestionId + "/status")
                        .header("Authorization", "Bearer " + teacherToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"new_status\":\"published\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void delete_draft_succeeds() throws Exception {
        MvcResult gen = mockMvc.perform(post("/api/v1/questions/generate")
                        .header("Authorization", "Bearer " + teacherToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"knowledge_id\":\"algebraic_expr\",\"difficulty\":4}"))
                .andExpect(status().isCreated())
                .andReturn();
        BigInteger id = BigInteger.valueOf(objectMapper.readTree(gen.getResponse().getContentAsString())
                .at("/data/id").asLong());

        mockMvc.perform(post("/api/v1/questions/" + id + "/delete")
                        .header("Authorization", "Bearer " + teacherToken))
                .andExpect(status().isNoContent());
    }

    private void registerAndPromote(String email, UserRole role) throws Exception {
        registerStudent(email);
        User user = userRepository.findByEmail(email).orElseThrow();
        user.setRole(role);
        userRepository.save(user);
    }

    private void registerStudent(String email) throws Exception {
        mockMvc.perform(post("/api/v1/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"" + email + "\",\"password\":\"password123\",\"name\":\"X\"}"))
                .andExpect(status().isCreated());
    }

    private String login(String email) throws Exception {
        LoginRequest login = new LoginRequest(email, "password123");
        MvcResult r = mockMvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(login)))
                .andExpect(status().isOk())
                .andReturn();
        return objectMapper.readTree(r.getResponse().getContentAsString())
                .at("/data/access_token").asText();
    }
}
