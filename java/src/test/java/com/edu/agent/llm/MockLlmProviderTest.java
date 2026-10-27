package com.edu.agent.llm;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

/**
 * MockLlmProvider 单元测试 -- 各场景格式与可用性。
 */
class MockLlmProviderTest {

    private final MockLlmProvider provider = new MockLlmProvider();

    @Test
    void isAvailable_alwaysFalse() {
        assertFalse(provider.isAvailable());
    }

    @Test
    void name_returnsMock() {
        assertEquals("mock", provider.name());
    }

    @Test
    void chat_criticScenario_returnsJson() {
        LlmRequest request = new LlmRequest(
                "You are a critic. Score pedagogical, appropriateness, clarity, engagement.",
                "Evaluate this answer");
        LlmResponse response = provider.chat(request);
        assertNotNull(response.content());
        assertTrue(response.content().contains("scores"));
        assertTrue(response.content().contains("pedagogical"));
        assertFalse(response.isError());
    }

    @Test
    void chat_questionScenario_returnsJson() {
        LlmRequest request = new LlmRequest(
                "Generate a multiple choice question with stem, options, correct_answer.",
                "Generate a question about algebra");
        LlmResponse response = provider.chat(request);
        assertTrue(response.content().contains("stem"));
        assertTrue(response.content().contains("options"));
        assertTrue(response.content().contains("correct_answer"));
    }

    @Test
    void chat_debateScenario_returnsJson() {
        LlmRequest request = new LlmRequest(
                "You are debating. Provide your stance and argument in debate format.",
                "Topic: Socratic vs Direct teaching");
        LlmResponse response = provider.chat(request);
        assertTrue(response.content().contains("argument"));
    }

    @Test
    void chat_tutorScenario_returnsGuidanceText() {
        LlmRequest request = new LlmRequest(
                "You are a tutor. Guide the student with questions.",
                "Student asks about algebra");
        LlmResponse response = provider.chat(request);
        assertNotNull(response.content());
        assertFalse(response.content().isEmpty());
        // Tutor response should contain guiding question markers
        assertTrue(response.content().contains("概念") || response.content().contains("思考"));
    }

    @Test
    void chat_modelIsMock() {
        LlmRequest request = new LlmRequest("system", "user");
        LlmResponse response = provider.chat(request);
        assertEquals("mock", response.model());
    }
}
