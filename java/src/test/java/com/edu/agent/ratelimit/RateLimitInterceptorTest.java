package com.edu.agent.ratelimit;

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

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * 限流拦截器测试:验证 429 响应 + Retry-After 头。
 */
@SpringBootTest(properties = "app.rate-limit.enabled=true")
@AutoConfigureMockMvc
@ActiveProfiles("test")
class RateLimitInterceptorTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Autowired
    UserRepository userRepository;

    @Autowired
    RateLimitInterceptor rateLimitInterceptor;

    @BeforeEach
    void clean() {
        userRepository.deleteAll();
        rateLimitInterceptor.resetForTest();
    }

    @Test
    void rapidLoginAttempts_return429AfterLimit() throws Exception {
        LoginRequest req = new LoginRequest("nobody@x.com", "wrong");

        // 第一次: 200 或 400(密码错),不是 429
        mockMvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isBadRequest());

        // 重置桶再试 5 次都失败,第 6 次应该 429
        rateLimitInterceptor.resetForTest();
        int limit = 5;
        for (int i = 0; i < limit; i++) {
            mockMvc.perform(post("/api/v1/auth/login")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(req)))
                    .andExpect(status().isBadRequest());
        }
        // 第 6 次: 429 + Retry-After 头存在
        mockMvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(req)))
                .andExpect(status().isTooManyRequests())
                .andExpect(header().exists("Retry-After"))
                .andExpect(header().exists("X-RateLimit-Limit"))
                .andExpect(header().exists("X-RateLimit-Remaining"));

        assertThat(rateLimitInterceptor.currentCount("login:127.0.0.1"))
                .isGreaterThanOrEqualTo(limit);
    }
}
