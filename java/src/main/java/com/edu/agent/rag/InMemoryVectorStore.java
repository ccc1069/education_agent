package com.edu.agent.rag;

import com.edu.agent.db.entity.DocumentChunk;
import com.edu.agent.db.repository.DocumentChunkRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;

import java.math.BigInteger;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 内存向量存储 -- 对齐 Python rag/vector_store.py InMemoryVectorStore。
 *
 * <p>全量加载 embedding 到内存,Java 计算 cosine 相似度。
 * 适用场景: 单元测试、小规模知识库(<10k chunks)、SQLite 部署。
 * 生产大规模知识库应切换到 PgVectorStore。
 */
@Slf4j
@Primary
@Component
@RequiredArgsConstructor
public class InMemoryVectorStore implements VectorStore {

    private final DocumentChunkRepository chunkRepository;

    // chunkId -> (chunk实体, embedding向量)
    private volatile Map<BigInteger, Entry> cache;

    @Override
    public List<ScoredChunk> search(List<Double> queryEmbedding, int topK, double minScore) {
        Map<BigInteger, Entry> data = cache;
        if (data == null) {
            data = load();
        }
        List<ScoredChunk> scored = new ArrayList<>();
        for (Entry e : data.values()) {
            double score = cosineSimilarity(queryEmbedding, e.embedding);
            if (score >= minScore) {
                scored.add(new ScoredChunk(
                        e.chunk.getId(),
                        e.chunk.getDocumentId(),
                        e.chunk.getContent(),
                        score,
                        e.chunk.getChunkIndex(),
                        e.chunk.getTokenCount(),
                        e.chunk.getMetadata(),
                        null,
                        null
                ));
            }
        }
        scored.sort((a, b) -> Double.compare(b.score(), a.score()));
        return scored.subList(0, Math.min(topK, scored.size()));
    }

    @Override
    public void invalidate() {
        cache = null;
    }

    private Map<BigInteger, Entry> load() {
        Map<BigInteger, Entry> data = new ConcurrentHashMap<>();
        List<DocumentChunk> all = chunkRepository.findAll();
        for (DocumentChunk c : all) {
            List<Double> emb = c.getEmbedding();
            if (emb != null && !emb.isEmpty()) {
                data.put(c.getId(), new Entry(c, emb));
            }
        }
        log.debug("InMemoryVectorStore loaded {} chunks", data.size());
        cache = data;
        return data;
    }

    /**
     * 余弦相似度 -- 对齐 Python cosine_similarity。
     * 返回 [-1, 1], 1 表示完全相似。
     */
    static double cosineSimilarity(List<Double> a, List<Double> b) {
        if (a == null || b == null || a.isEmpty() || b.isEmpty() || a.size() != b.size()) {
            return 0.0;
        }
        double dot = 0, normA = 0, normB = 0;
        for (int i = 0; i < a.size(); i++) {
            double x = a.get(i);
            double y = b.get(i);
            dot += x * y;
            normA += x * x;
            normB += y * y;
        }
        if (normA == 0 || normB == 0) return 0.0;
        return dot / (Math.sqrt(normA) * Math.sqrt(normB));
    }

    /** package-private 用于同包测试。 */
    record Entry(DocumentChunk chunk, List<Double> embedding) {}
}
