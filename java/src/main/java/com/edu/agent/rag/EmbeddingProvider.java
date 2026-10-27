package com.edu.agent.rag;

import java.util.List;

/**
 * Embedding 提供者抽象 -- 对齐 Python rag/embedding.py。
 *
 * <p>两种实现:
 * <ul>
 *   <li>{@link MockEmbeddingProvider}: 基于哈希的确定性 384 维向量(测试/无 API key)</li>
 *   <li>{@link OpenAIEmbeddingProvider}: 调用 OpenAI 兼容 /embeddings 接口</li>
 * </ul>
 */
public interface EmbeddingProvider {

    /** 提供者名称: "mock" 或 "openai_compatible"。 */
    String name();

    /** 向量维度(如 384 / 1536 / 3072)。 */
    int dimension();

    /** 单文本 -> 向量。 */
    List<Double> embed(String text);

    /** 批量 embed(性能更好)。 */
    List<List<Double>> embedBatch(List<String> texts);
}
