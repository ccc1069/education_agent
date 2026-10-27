package com.edu.agent.llm;

import org.junit.jupiter.api.Test;

import java.lang.reflect.Field;

import static org.junit.jupiter.api.Assertions.*;

/**
 * OpenAiLlmProvider 单元测试 -- 可用性检查与错误处理。
 */
class OpenAiLlmProviderTest {

    private OpenAiLlmProvider createProvider(String apiKey, String baseUrl) {
        return new OpenAiLlmProvider(apiKey, baseUrl, "gpt-4o-mini", 30);
    }

    @Test
    void isAvailable_withBlankKey_returnsFalse() {
        OpenAiLlmProvider provider = createProvider("", "https://api.openai.com/v1");
        assertFalse(provider.isAvailable());
    }

    @Test
    void isAvailable_withNullKey_returnsFalse() {
        OpenAiLlmProvider provider = createProvider(null, "https://api.openai.com/v1");
        assertFalse(provider.isAvailable());
    }

    @Test
    void isAvailable_withValidKey_returnsTrue() {
        OpenAiLlmProvider provider = createProvider("sk-test123", "https://api.openai.com/v1");
        assertTrue(provider.isAvailable());
    }

    @Test
    void name_returnsOpenai() {
        OpenAiLlmProvider provider = createProvider("sk-test", "https://api.openai.com/v1");
        assertEquals("openai", provider.name());
    }

    @Test
    void chat_withBlankKey_throwsException() {
        OpenAiLlmProvider provider = createProvider("", "https://api.openai.com/v1");
        LlmRequest request = new LlmRequest("system", "user");
        assertThrows(LlmUnavailableException.class, () -> provider.chat(request));
    }

    @Test
    void baseUrl_trailingSlash_stripped() throws Exception {
        OpenAiLlmProvider provider = createProvider("sk-test", "https://api.openai.com/v1/");
        // Verify baseUrl field has no trailing slash via reflection
        Field field = OpenAiLlmProvider.class.getDeclaredField("baseUrl");
        field.setAccessible(true);
        String baseUrl = (String) field.get(provider);
        assertFalse(baseUrl.endsWith("/"));
    }

    @Test
    void chat_withInvalidUrl_throwsLlmUnavailableException() {
        OpenAiLlmProvider provider = createProvider("sk-test", "http://localhost:19999/v1");
        LlmRequest request = new LlmRequest("system", "user");
        // Connection refused should throw LlmUnavailableException
        assertThrows(LlmUnavailableException.class, () -> provider.chat(request));
    }
}
