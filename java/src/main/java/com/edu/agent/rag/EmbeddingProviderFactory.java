package com.edu.agent.rag;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * Embedding 提供者工厂 -- 对齐 Python rag/embedding.py get_embedding_provider。
 *
 * <p>根据配置选择提供者:
 * <ul>
 *   <li>provider=mock -> {@link MockEmbeddingProvider}(确定性,无外部依赖,测试/开发用)</li>
 *   <li>provider=openai -> {@link OpenAIEmbeddingProvider}(调用 /embeddings API)</li>
 *   <li>无 API key 时自动回退到 mock</li>
 * </ul>
 */
@Slf4j
@Component
public class EmbeddingProviderFactory {

    private final String provider;
    private final String apiKey;

    public EmbeddingProviderFactory(
            @Value("${app.embedding.provider:mock}") String provider,
            @Value("${app.embedding.api-key:}") String apiKey) {
        this.provider = provider;
        this.apiKey = apiKey;
    }

    public EmbeddingProvider create() {
        if ("openai".equalsIgnoreCase(provider) && apiKey != null && !apiKey.isBlank()) {
            log.info("Using OpenAIEmbeddingProvider (model=openai_compatible)");
            return new OpenAIEmbeddingProvider(
                    "https://api.openai.com/v1", apiKey,
                    "text-embedding-3-small", 1536);
        }
        log.info("Using MockEmbeddingProvider (dim={})", MockEmbeddingProvider.DIM);
        return new MockEmbeddingProvider();
    }
}
