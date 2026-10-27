package com.edu.agent.rag;

import java.math.BigInteger;
import java.util.List;
import java.util.Map;

/**
 * 向量存储抽象 -- 对齐 Python rag/vector_store.py。
 *
 * <p>两种实现:
 * <ul>
 *   <li>{@link InMemoryVectorStore}: 全量加载到内存,Java cosine 相似度(测试/小规模)</li>
 *   <li>PgVectorStore(预留): pgvector 原生搜索(生产)</li>
 * </ul>
 */
public interface VectorStore {

    /**
     * 检索最相似的 top_k 个 chunk。
     *
     * @param queryEmbedding 查询向量
     * @param topK           最多返回条数
     * @param minScore       最低余弦相似度阈值
     * @return 命中的 chunk 列表(按相似度降序)
     */
    List<ScoredChunk> search(List<Double> queryEmbedding, int topK, double minScore);

    /** 清除内存缓存(如有)。 */
    default void invalidate() {}

    /** 检索结果。 */
    record ScoredChunk(
            BigInteger chunkId,
            BigInteger documentId,
            String content,
            double score,
            int chunkIndex,
            int tokenCount,
            Map<String, Object> metadata,
            String documentTitle,
            String documentSourceType
    ) {}
}
