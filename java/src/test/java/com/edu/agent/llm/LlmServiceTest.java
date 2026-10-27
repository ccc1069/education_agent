package com.edu.agent.llm;

import com.edu.agent.observability.AgentMetrics;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/**
 * LlmService 单元测试 -- 重试/熔断/降级逻辑。
 */
@ExtendWith(MockitoExtension.class)
class LlmServiceTest {

    @Mock
    private LlmProviderFactory providerFactory;

    @Mock
    private AgentMetrics metrics;

    @Mock
    private LlmProvider mockProvider;

    private LlmService llmService;

    @BeforeEach
    void setUp() {
        llmService = new LlmService(providerFactory, metrics, 3, 100, 5, 60);
    }

    private LlmRequest sampleRequest() {
        return new LlmRequest("system", "user");
    }

    @Test
    void chat_successOnFirstAttempt_returnsResponse() {
        LlmResponse expected = new LlmResponse("hello", "gpt-4o-mini", 10, 5, 15, "stop", 100.0);
        when(providerFactory.getProvider()).thenReturn(mockProvider);
        when(mockProvider.chat(any())).thenReturn(expected);
        when(mockProvider.name()).thenReturn("openai");

        LlmResponse result = llmService.chat(sampleRequest());

        assertEquals("hello", result.content());
        assertEquals("gpt-4o-mini", result.model());
        verify(metrics).recordLlmTokens(eq("openai"), eq("gpt-4o-mini"), eq("prompt"), eq(10L));
    }

    @Test
    void chat_retriesOnFailure_thenSucceeds() {
        LlmResponse expected = new LlmResponse("recovered", "gpt-4o-mini", 10, 5, 15, "stop", 100.0);
        when(providerFactory.getProvider()).thenReturn(mockProvider);
        when(mockProvider.name()).thenReturn("openai");
        when(mockProvider.chat(any()))
                .thenThrow(new LlmUnavailableException("server error"))
                .thenReturn(expected);

        LlmService service = new LlmService(providerFactory, metrics, 3, 10, 5, 60);

        LlmResponse result = service.chat(sampleRequest());

        assertEquals("recovered", result.content());
        verify(mockProvider, times(2)).chat(any());
    }

    @Test
    void chat_retriesExhausted_throwsException() {
        when(providerFactory.getProvider()).thenReturn(mockProvider);
        when(mockProvider.name()).thenReturn("openai");
        when(mockProvider.chat(any())).thenThrow(new LlmUnavailableException("server error"));

        LlmService service = new LlmService(providerFactory, metrics, 2, 10, 5, 60);

        assertThrows(LlmUnavailableException.class, () -> service.chat(sampleRequest()));
        verify(mockProvider, times(2)).chat(any());
    }

    @Test
    void chat_circuitBreakerOpensAfterThreshold() {
        when(providerFactory.getProvider()).thenReturn(mockProvider);
        when(mockProvider.name()).thenReturn("openai");
        when(mockProvider.chat(any())).thenThrow(new LlmUnavailableException("error"));

        // threshold=2, so after 2 consecutive failures circuit opens
        LlmService service = new LlmService(providerFactory, metrics, 1, 10, 2, 60);

        assertThrows(LlmUnavailableException.class, () -> service.chat(sampleRequest()));
        assertThrows(LlmUnavailableException.class, () -> service.chat(sampleRequest()));

        // Circuit should be open now
        LlmUnavailableException ex = assertThrows(LlmUnavailableException.class,
                () -> service.chat(sampleRequest()));
        assertTrue(ex.getMessage().contains("熔断器断开"));
    }

    @Test
    void chatOrFallback_returnsNullOnFailure() {
        when(providerFactory.getProvider()).thenReturn(mockProvider);
        when(mockProvider.name()).thenReturn("openai");
        when(mockProvider.chat(any())).thenThrow(new LlmUnavailableException("error"));

        LlmService service = new LlmService(providerFactory, metrics, 1, 10, 10, 60);

        String result = service.chatOrFallback(sampleRequest());
        assertNull(result);
    }

    @Test
    void chatOrFallback_returnsContentOnSuccess() {
        LlmResponse expected = new LlmResponse("LLM says hi", "gpt-4o-mini", 5, 3, 8, "stop", 50.0);
        when(providerFactory.getProvider()).thenReturn(mockProvider);
        when(mockProvider.chat(any())).thenReturn(expected);
        when(mockProvider.name()).thenReturn("openai");

        String result = llmService.chatOrFallback(sampleRequest());
        assertEquals("LLM says hi", result);
    }

    @Test
    void circuitBreaker_resetsAfterSuccess() {
        LlmResponse ok = new LlmResponse("ok", "gpt-4o-mini", 5, 3, 8, "stop", 50.0);
        when(providerFactory.getProvider()).thenReturn(mockProvider);
        when(mockProvider.name()).thenReturn("openai");
        when(mockProvider.chat(any()))
                .thenThrow(new LlmUnavailableException("error"))
                .thenReturn(ok);

        LlmService service = new LlmService(providerFactory, metrics, 1, 10, 2, 60);

        // 1 failure (below threshold of 2)
        assertThrows(LlmUnavailableException.class, () -> service.chat(sampleRequest()));
        // Success resets counter
        LlmResponse result = service.chat(sampleRequest());
        assertEquals("ok", result.content());
    }
}
