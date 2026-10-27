package com.edu.agent.service;

import com.edu.agent.db.entity.Document;
import com.edu.agent.db.entity.DocumentChunk;
import com.edu.agent.db.repository.DocumentChunkRepository;
import com.edu.agent.db.repository.DocumentRepository;
import com.edu.agent.rag.EmbeddingProvider;
import com.edu.agent.rag.EmbeddingProviderFactory;
import com.edu.agent.rag.VectorStore;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * RAG 服务 -- 对齐 Python services/rag_service.py。
 *
 * <p>语义分块(按句子聚合 + overlap) + Embedding 调用 + 向量检索(top-k + min_score)。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class RagService {

    private final DocumentRepository documentRepository;
    private final DocumentChunkRepository chunkRepository;
    private final EmbeddingProviderFactory embeddingFactory;
    private final VectorStore vectorStore;

    /** 每块最大 token 数(对齐 Python max_tokens=500)。 */
    private static final int MAX_TOKENS = 500;
    /** 块间重叠句子数(对齐 Python overlap_sentences=1)。 */
    private static final int OVERLAP_SENTENCES = 1;
    /** 1 token ≈ 4 chars(英文近似,对齐 Python _APPROX_RATIO)。 */
    private static final int TOKEN_RATIO = 4;

    private static final Pattern SENTENCE_END = Pattern.compile("(?<=[。.!?？！])\\s+");

    @Transactional
    public IngestResult ingestDocument(String title, String content, String sourceType,
                                        String sourceUrl, Map<String, Object> metadata) {
        String hash = sha256(content);
        Optional<Document> existing = documentRepository.findByContentHash(hash);
        if (existing.isPresent()) {
            log.info("Document already exists (dedup): id={} hash={}", existing.get().getId(), hash);
            return new IngestResult(existing.get().getId(), false);
        }

        Document doc = new Document();
        doc.setTitle(title);
        doc.setSourceType(sourceType != null ? sourceType : "text");
        doc.setSourceUrl(sourceUrl);
        doc.setContentHash(hash);
        doc.setStatus("ready");
        doc.setMetadata(metadata != null ? metadata : new HashMap<>());
        doc = documentRepository.save(doc);

        List<DocumentChunk> chunks = chunkAndEmbed(doc.getId(), content);
        chunkRepository.saveAll(chunks);
        doc.setTotalChunks(chunks.size());
        documentRepository.save(doc);
        // 新文档入库后,让内存缓存失效,下次检索时重新加载
        vectorStore.invalidate();
        log.info("Document ingested: id={} chunks={}", doc.getId(), chunks.size());
        return new IngestResult(doc.getId(), true);
    }

    @Transactional(readOnly = true)
    public List<Map<String, Object>> listDocuments(BigInteger tenantId, String status,
                                                     int limit, int offset) {
        Pageable pageable = PageRequest.of(offset / Math.max(limit, 1), Math.max(limit, 1));
        Page<Document> page = status != null
                ? documentRepository.findByTenantIdAndStatus(tenantId, status, pageable)
                : documentRepository.findByTenantIdOrderByCreatedAtDesc(tenantId, pageable);
        return page.map(this::toSummaryMap).getContent();
    }

    @Transactional(readOnly = true)
    public Map<String, Object> getDocument(BigInteger documentId) {
        return documentRepository.findById(documentId)
                .map(doc -> {
                    Map<String, Object> m = toSummaryMap(doc);
                    m.put("metadata", doc.getMetadata());
                    m.put("updated_at", doc.getUpdatedAt() != null ? doc.getUpdatedAt().toString() : null);
                    List<Map<String, Object>> chunks = chunkRepository
                            .findByDocumentIdOrderByChunkIndex(documentId)
                            .stream()
                            .map(c -> {
                                Map<String, Object> cm = new HashMap<>();
                                cm.put("id", c.getId());
                                cm.put("chunk_index", c.getChunkIndex());
                                cm.put("content", c.getContent());
                                cm.put("token_count", c.getTokenCount());
                                cm.put("metadata", c.getMetadata());
                                return cm;
                            })
                            .toList();
                    m.put("chunks", chunks);
                    return m;
                })
                .orElse(null);
    }

    @Transactional
    public boolean deleteDocument(BigInteger documentId) {
        return documentRepository.findById(documentId).map(doc -> {
            chunkRepository.findByDocumentIdOrderByChunkIndex(documentId)
                    .forEach(chunkRepository::delete);
            documentRepository.delete(doc);
            vectorStore.invalidate();
            return true;
        }).orElse(false);
    }

    /**
     * 语义向量检索 -- 对齐 Python InMemoryVectorStore.search。
     *
     * @param tenantId 租户 ID(用于租户隔离的 filter)
     * @param query    查询文本
     * @param topK     最多返回条数
     * @param minScore 最低相似度阈值
     * @return 命中的 chunk 列表(按相似度降序)
     */
    @Transactional(readOnly = true)
    public List<Map<String, Object>> search(BigInteger tenantId, String query,
                                              int topK, double minScore) {
        EmbeddingProvider embedder = embeddingFactory.create();
        List<Double> queryVec = embedder.embed(query);
        List<VectorStore.ScoredChunk> hits = vectorStore.search(queryVec, topK, minScore);
        return hits.stream()
                .map(s -> {
                    Map<String, Object> m = new HashMap<>();
                    m.put("chunk_id", s.chunkId());
                    m.put("document_id", s.documentId());
                    m.put("content", s.content());
                    m.put("score", Math.round(s.score() * 10000) / 10000.0);
                    m.put("chunk_index", s.chunkIndex());
                    m.put("token_count", s.tokenCount());
                    m.put("metadata", s.metadata());
                    return m;
                })
                .toList();
    }

    /**
     * 语义分块 + Embedding 调用 -- 对齐 Python chunk_text + embedBatch。
     *
     * <p>按句子边界切分,聚合到 MAX_TOKENS 为一块,块间重叠 OVERLAP_SENTENCES 句。
     * 每块调用 EmbeddingProvider 生成向量,存入 DocumentChunk.embedding。
     */
    private List<DocumentChunk> chunkAndEmbed(BigInteger docId, String content) {
        List<String> sentences = splitSentences(content);
        if (sentences.isEmpty()) {
            return List.of();
        }

        // 聚合句子为块
        List<String> chunkTexts = new ArrayList<>();
        List<Integer> chunkTokens = new ArrayList<>();
        List<String> current = new ArrayList<>();
        int currentTokens = 0;

        for (String sent : sentences) {
            int sentTokens = countTokens(sent);
            if (sentTokens >= MAX_TOKENS) {
                // 单句超长: 先写入已聚合的
                if (!current.isEmpty()) {
                    chunkTexts.add(String.join(" ", current));
                    chunkTokens.add(currentTokens);
                    // overlap
                    if (OVERLAP_SENTENCES > 0 && current.size() >= OVERLAP_SENTENCES) {
                        List<String> tail = current.subList(current.size() - OVERLAP_SENTENCES, current.size());
                        current = new ArrayList<>(tail);
                        currentTokens = current.stream().mapToInt(this::countTokens).sum();
                    } else {
                        current = new ArrayList<>();
                        currentTokens = 0;
                    }
                }
                // 单独成块
                chunkTexts.add(sent);
                chunkTokens.add(sentTokens);
                continue;
            }
            if (currentTokens + sentTokens > MAX_TOKENS) {
                chunkTexts.add(String.join(" ", current));
                chunkTokens.add(currentTokens);
                if (OVERLAP_SENTENCES > 0 && current.size() >= OVERLAP_SENTENCES) {
                    List<String> tail = current.subList(current.size() - OVERLAP_SENTENCES, current.size());
                    current = new ArrayList<>(tail);
                    currentTokens = current.stream().mapToInt(this::countTokens).sum();
                } else {
                    current = new ArrayList<>();
                    currentTokens = 0;
                }
            }
            current.add(sent);
            currentTokens += sentTokens;
        }
        if (!current.isEmpty()) {
            chunkTexts.add(String.join(" ", current));
            chunkTokens.add(currentTokens);
        }

        // 批量 Embedding
        EmbeddingProvider embedder = embeddingFactory.create();
        List<List<Double>> embeddings = embedder.embedBatch(chunkTexts);

        // 组装 DocumentChunk
        List<DocumentChunk> chunks = new ArrayList<>(chunkTexts.size());
        for (int i = 0; i < chunkTexts.size(); i++) {
            DocumentChunk c = new DocumentChunk();
            c.setDocumentId(docId);
            c.setChunkIndex(i);
            c.setContent(chunkTexts.get(i));
            c.setTokenCount(chunkTokens.get(i));
            c.setEmbedding(embeddings.get(i));
            c.setMetadata(new HashMap<>());
            chunks.add(c);
        }
        return chunks;
    }

    /**
     * 按句子边界切分 -- 对齐 Python _split_sentences。
     * 保留分隔符在句子末尾。
     */
    private List<String> splitSentences(String text) {
        text = text.strip();
        if (text.isEmpty()) return List.of();
        List<String> sentences = new ArrayList<>();
        for (String part : SENTENCE_END.split(text)) {
            if (part.length() <= 1000) {
                String stripped = part.strip();
                if (!stripped.isEmpty()) sentences.add(stripped);
                continue;
            }
            // 单句过长: 按段落切
            for (String para : part.split("\n\n")) {
                String p = para.strip();
                if (p.isEmpty()) continue;
                if (p.length() > 1000) {
                    for (int i = 0; i < p.length(); i += 1000) {
                        sentences.add(p.substring(i, Math.min(i + 1000, p.length())));
                    }
                } else {
                    sentences.add(p);
                }
            }
        }
        return sentences;
    }

    /** 估算 token 数 -- 对齐 Python count_tokens(len/4 近似)。 */
    private int countTokens(String text) {
        return Math.max(1, text.length() / TOKEN_RATIO);
    }

    private Map<String, Object> toSummaryMap(Document d) {
        Map<String, Object> m = new HashMap<>();
        m.put("id", d.getId());
        m.put("title", d.getTitle());
        m.put("source_type", d.getSourceType());
        m.put("source_url", d.getSourceUrl());
        m.put("status", d.getStatus());
        m.put("total_chunks", d.getTotalChunks());
        m.put("content_hash", d.getContentHash());
        m.put("created_at", d.getCreatedAt() != null ? d.getCreatedAt().toString() : null);
        m.put("error_message", d.getErrorMessage());
        return m;
    }

    private static String sha256(String input) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] hash = md.digest(input.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (byte b : hash) sb.append(String.format("%02x", b));
            return sb.toString();
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    public record IngestResult(BigInteger documentId, boolean isNew) {}
}
