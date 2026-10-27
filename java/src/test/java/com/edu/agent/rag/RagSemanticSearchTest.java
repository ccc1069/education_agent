package com.edu.agent.rag;

import com.edu.agent.db.entity.DocumentChunk;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.math.BigInteger;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

/**
 * RAG 语义检索单元测试: 验证 MockEmbeddingProvider + InMemoryVectorStore 集成。
 *
 * <p>使用确定性 embedding,验证:
 * <ul>
 *   <li>语义相关查询命中文档</li>
 *   <li>topK 限制正确</li>
 *   <li>minScore 阈值过滤正确</li>
 *   <li>余弦相似度排序正确</li>
 * </ul>
 */
class RagSemanticSearchTest {

    private InMemoryVectorStore store;

    @BeforeEach
    void setUp() {
        // 用 mock repository 数据直接测试 VectorStore
        store = new InMemoryVectorStore(null);
        seedChunks();
    }

    @Test
    void exactQuery_returnsIdenticalChunkFirst() {
        EmbeddingProvider mock = new MockEmbeddingProvider();
        // 用 chunk 原文做查询 -> 余弦相似度 = 1.0,必然排第一
        String exactText = "Python 是一种高级编程语言,强调代码可读性和简洁语法。";
        List<Double> queryVec = mock.embed(exactText);
        List<VectorStore.ScoredChunk> hits = store.search(queryVec, 3, 0.0);
        assertThat(hits).isNotEmpty();
        assertThat(hits.get(0).content()).isEqualTo(exactText);
        assertThat(hits.get(0).score()).isCloseTo(1.0, within(0.001));
    }

    @Test
    void secondChunkQuery_returnsSecondChunkFirst() {
        EmbeddingProvider mock = new MockEmbeddingProvider();
        // 用 chunk 3 原文查询 -> chunk 3 必然排第一(相似度 1.0)
        String chunk3Text = "机器学习是人工智能的一个分支,通过数据训练模型进行预测。";
        List<Double> queryVec = mock.embed(chunk3Text);
        List<VectorStore.ScoredChunk> hits = store.search(queryVec, 4, 0.0);
        assertThat(hits).isNotEmpty();
        assertThat(hits.get(0).content()).isEqualTo(chunk3Text);
        assertThat(hits.get(0).score()).isCloseTo(1.0, within(0.001));
    }

    @Test
    void topK_limitsResults() {
        EmbeddingProvider mock = new MockEmbeddingProvider();
        List<Double> queryVec = mock.embed("data");
        List<VectorStore.ScoredChunk> hits = store.search(queryVec, 2, 0.0);
        assertThat(hits.size()).isLessThanOrEqualTo(2);
    }

    @Test
    void minScore_filtersLowSimilarity() {
        EmbeddingProvider mock = new MockEmbeddingProvider();
        List<Double> queryVec = mock.embed("xyzqwk999");
        // 高阈值应该过滤掉不相关的结果
        List<VectorStore.ScoredChunk> hits = store.search(queryVec, 10, 0.99);
        assertThat(hits).isEmpty();
    }

    @Test
    void results_sortedByScoreDesc() {
        EmbeddingProvider mock = new MockEmbeddingProvider();
        List<Double> queryVec = mock.embed("machine learning");
        List<VectorStore.ScoredChunk> hits = store.search(queryVec, 5, 0.0);
        for (int i = 1; i < hits.size(); i++) {
            assertThat(hits.get(i - 1).score())
                    .isGreaterThanOrEqualTo(hits.get(i).score());
        }
    }

    @Test
    void cosineSimilarity_identicalVectors_returnsOne() {
        List<Double> v = List.of(1.0, 2.0, 3.0);
        double sim = InMemoryVectorStore.cosineSimilarity(v, v);
        assertThat(sim).isCloseTo(1.0, within(0.001));
    }

    @Test
    void cosineSimilarity_orthogonalVectors_returnsZero() {
        List<Double> a = List.of(1.0, 0.0, 0.0);
        List<Double> b = List.of(0.0, 1.0, 0.0);
        double sim = InMemoryVectorStore.cosineSimilarity(a, b);
        assertThat(sim).isCloseTo(0.0, within(0.001));
    }

    @Test
    void mockEmbedding_deterministic() {
        MockEmbeddingProvider mock = new MockEmbeddingProvider();
        List<Double> v1 = mock.embed("hello world");
        List<Double> v2 = mock.embed("hello world");
        assertThat(v1).isEqualTo(v2);
    }

    @Test
    void mockEmbedding_dimensionIs384() {
        MockEmbeddingProvider mock = new MockEmbeddingProvider();
        assertThat(mock.dimension()).isEqualTo(384);
        assertThat(mock.embed("test")).hasSize(384);
    }

    @Test
    void mockEmbedding_differentTexts_differentVectors() {
        MockEmbeddingProvider mock = new MockEmbeddingProvider();
        List<Double> v1 = mock.embed("python");
        List<Double> v2 = mock.embed("javascript");
        assertThat(v1).isNotEqualTo(v2);
    }

    /** 注入测试数据到 store 的缓存(绕过 repository)。 */
    private void seedChunks() {
        Map<BigInteger, InMemoryVectorStore.Entry> data = new HashMap<>();
        MockEmbeddingProvider mock = new MockEmbeddingProvider();

        data.put(BigInteger.ONE, new InMemoryVectorStore.Entry(
                makeChunk(BigInteger.ONE, "Python 是一种高级编程语言,强调代码可读性和简洁语法。"),
                mock.embed("Python 是一种高级编程语言,强调代码可读性和简洁语法。")));
        data.put(BigInteger.valueOf(2), new InMemoryVectorStore.Entry(
                makeChunk(BigInteger.valueOf(2), "JavaScript 是 Web 开发的脚本语言,可运行在浏览器和服务器端。"),
                mock.embed("JavaScript 是 Web 开发的脚本语言,可运行在浏览器和服务器端。")));
        data.put(BigInteger.valueOf(3), new InMemoryVectorStore.Entry(
                makeChunk(BigInteger.valueOf(3), "机器学习是人工智能的一个分支,通过数据训练模型进行预测。"),
                mock.embed("机器学习是人工智能的一个分支,通过数据训练模型进行预测。")));
        data.put(BigInteger.valueOf(4), new InMemoryVectorStore.Entry(
                makeChunk(BigInteger.valueOf(4), "数据库索引能加速查询,B+ 树是常见的数据结构。"),
                mock.embed("数据库索引能加速查询,B+ 树是常见的数据结构。")));

        // 通过 invalidate + 反射注入 cache(测试用)
        injectCache(data);
    }

    private DocumentChunk makeChunk(BigInteger id, String content) {
        DocumentChunk c = new DocumentChunk();
        c.setId(id);
        c.setDocumentId(BigInteger.valueOf(100));
        c.setChunkIndex(id.intValue() - 1);
        c.setContent(content);
        c.setTokenCount(content.length() / 4);
        c.setMetadata(new HashMap<>());
        return c;
    }

    @SuppressWarnings("unchecked")
    private void injectCache(Map<BigInteger, InMemoryVectorStore.Entry> data) {
        try {
            java.lang.reflect.Field f = InMemoryVectorStore.class.getDeclaredField("cache");
            f.setAccessible(true);
            f.set(store, data);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }
}
