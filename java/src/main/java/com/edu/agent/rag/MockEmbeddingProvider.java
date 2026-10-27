package com.edu.agent.rag;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;

/**
 * Mock Embedding: 基于文本哈希的确定性向量。
 *
 * <p>对齐 Python MockEmbeddingProvider:
 * <ul>
 *   <li>384 维(与 sentence-transformers MiniLM 一致)</li>
 *   <li>确定性: 相同文本 -> 相同向量</li>
 *   <li>语义近似: 共享子串的文本余弦相似度较高</li>
 * </ul>
 */
public class MockEmbeddingProvider implements EmbeddingProvider {

    public static final int DIM = 384;

    @Override
    public String name() {
        return "mock";
    }

    @Override
    public int dimension() {
        return DIM;
    }

    @Override
    public List<Double> embed(String text) {
        return hashToVector(text);
    }

    @Override
    public List<List<Double>> embedBatch(List<String> texts) {
        List<List<Double>> out = new ArrayList<>(texts.size());
        for (String t : texts) {
            out.add(hashToVector(t));
        }
        return out;
    }

    private void addHash(double[] vec, String token) {
        try {
            MessageDigest md = MessageDigest.getInstance("MD5");
            byte[] h = md.digest(token.getBytes(StandardCharsets.UTF_8));
            for (int i = 0; i < DIM; i += 4) {
                int chunk = h[i % 16] & 0xFF;
                chunk = (chunk << 8) | (h[(i % 16 + 1) % 16] & 0xFF);
                chunk = (chunk << 8) | (h[(i % 16 + 2) % 16] & 0xFF);
                chunk = (chunk << 8) | (h[(i % 16 + 3) % 16] & 0xFF);
                double value = chunk / (double) 0xFFFFFFFF - 0.5;
                vec[i] += value;
            }
        } catch (Exception e) {
            // MD5 always available
        }
    }

    private List<Double> hashToVector(String text) {
        double[] vec = new double[DIM];
        String lower = text.toLowerCase().strip();
        if (lower.isEmpty()) {
            return toList(vec);
        }

        // 词级哈希
        for (String word : lower.split("\\s+")) {
            addHash(vec, word);
        }
        // 字符 2-gram 哈希(中文/混合)
        String chars = String.join("", lower.split("\\s+"));
        for (int i = 0; i < chars.length() - 1; i++) {
            addHash(vec, chars.substring(i, i + 2));
        }

        // L2 归一化
        double norm = 0;
        for (double v : vec) norm += v * v;
        norm = Math.sqrt(norm);
        if (norm == 0) norm = 1;
        for (int i = 0; i < DIM; i++) vec[i] /= norm;
        return toList(vec);
    }

    private static List<Double> toList(double[] arr) {
        List<Double> list = new ArrayList<>(arr.length);
        for (double v : arr) list.add(v);
        return list;
    }
}
