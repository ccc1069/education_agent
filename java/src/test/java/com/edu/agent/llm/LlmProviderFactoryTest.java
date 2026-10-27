package com.edu.agent.llm;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/**
 * LlmProviderFactory 单元测试 -- provider 选择逻辑。
 */
@ExtendWith(MockitoExtension.class)
class LlmProviderFactoryTest {

    @Mock
    private OpenAiLlmProvider openAiProvider;

    @Mock
    private MockLlmProvider mockProvider;

    @Test
    void auto_withOpenAiKey_returnsOpenAiProvider() {
        when(openAiProvider.isAvailable()).thenReturn(true);
        LlmProviderFactory factory = new LlmProviderFactory(openAiProvider, mockProvider, "auto");

        LlmProvider result = factory.getProvider();
        assertEquals(openAiProvider, result);
        assertTrue(factory.isRealLlmEnabled());
    }

    @Test
    void auto_withoutKey_returnsMockProvider() {
        when(openAiProvider.isAvailable()).thenReturn(false);
        LlmProviderFactory factory = new LlmProviderFactory(openAiProvider, mockProvider, "auto");

        LlmProvider result = factory.getProvider();
        assertEquals(mockProvider, result);
        assertFalse(factory.isRealLlmEnabled());
    }

    @Test
    void explicitOpenAi_returnsOpenAiProvider() {
        LlmProviderFactory factory = new LlmProviderFactory(openAiProvider, mockProvider, "openai");

        LlmProvider result = factory.getProvider();
        assertEquals(openAiProvider, result);
        verify(openAiProvider, never()).isAvailable(); // explicit mode doesn't check
    }

    @Test
    void explicitMock_returnsMockProvider() {
        LlmProviderFactory factory = new LlmProviderFactory(openAiProvider, mockProvider, "mock");

        LlmProvider result = factory.getProvider();
        assertEquals(mockProvider, result);
        assertFalse(factory.isRealLlmEnabled());
    }

    @Test
    void blankConfig_defaultsToAuto() {
        when(openAiProvider.isAvailable()).thenReturn(true);
        LlmProviderFactory factory = new LlmProviderFactory(openAiProvider, mockProvider, "");

        LlmProvider result = factory.getProvider();
        assertEquals(openAiProvider, result);
    }
}
