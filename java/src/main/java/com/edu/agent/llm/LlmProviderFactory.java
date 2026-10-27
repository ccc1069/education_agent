package com.edu.agent.llm;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * LLM Provider 工厂 -- 按配置选择 provider(对齐 Python llm.factory.get_llm_provider)。
 *
 * <p>配置项 {@code app.llm.provider}:
 * <ul>
 *   <li>{@code auto}(默认):有 OpenAI key 用 OpenAI,否则用 Mock</li>
 *   <li>{@code openai}:强制使用 OpenAI</li>
 *   <li>{@code mock}:强制使用 Mock</li>
 * </ul>
 */
@Component
public class LlmProviderFactory {

    private static final Logger log = LoggerFactory.getLogger(LlmProviderFactory.class);

    private final OpenAiLlmProvider openAiProvider;
    private final MockLlmProvider mockProvider;
    private final String configuredProvider;

    public LlmProviderFactory(
            OpenAiLlmProvider openAiProvider,
            MockLlmProvider mockProvider,
            @Value("${app.llm.provider:auto}") String configuredProvider) {
        this.openAiProvider = openAiProvider;
        this.mockProvider = mockProvider;
        this.configuredProvider = configuredProvider.isBlank() ? "auto" : configuredProvider;
    }

    /**
     * 获取按配置选择的 provider。
     */
    public LlmProvider getProvider() {
        return switch (configuredProvider) {
            case "openai" -> {
                log.debug("[LlmProviderFactory] 使用 OpenAI provider");
                yield openAiProvider;
            }
            case "mock" -> {
                log.debug("[LlmProviderFactory] 使用 Mock provider");
                yield mockProvider;
            }
            default -> {
                // auto:优先 OpenAI(有 key 时)
                if (openAiProvider.isAvailable()) {
                    log.debug("[LlmProviderFactory] auto 模式:OpenAI key 已配置,使用 OpenAI provider");
                    yield openAiProvider;
                }
                log.debug("[LlmProviderFactory] auto 模式:无 OpenAI key,降级到 Mock provider");
                yield mockProvider;
            }
        };
    }

    /**
     * 是否使用真实 LLM(供调用方判断是否需要降级逻辑)。
     */
    public boolean isRealLlmEnabled() {
        return "mock".equals(configuredProvider) ? false
                : openAiProvider.isAvailable();
    }
}
