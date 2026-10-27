package com.edu.agent.rag;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * OpenAI 兼容 Embedding 提供者 -- 对齐 Python rag/embedding.py OpenAIEmbeddingProvider。
 *
 * <p>调用 /embeddings 接口,支持任意 OpenAI 兼容服务(Ollama、MiniMax、DeepSeek 等)。
 * 配置:
 * <pre>
 *   app.embedding.provider=openai
 *   app.embedding.api-key=sk-xxx
 *   app.embedding.base-url=https://api.openai.com/v1
 *   app.embedding.model=text-embedding-3-small
 *   app.embedding.dimensions=1536
 * </pre>
 */
@Slf4j
@Component
public class OpenAIEmbeddingProvider implements EmbeddingProvider {

    private static final Pattern NUMBER = Pattern.compile("-?\\d+(?:\\.\\d+)?(?:[eE][+-]?\\d+)?");

    private final String baseUrl;
    private final String apiKey;
    private final String model;
    private final int dimensions;
    private final HttpClient http;

    public OpenAIEmbeddingProvider(
            @Value("${app.embedding.base-url:https://api.openai.com/v1}") String baseUrl,
            @Value("${app.embedding.api-key:}") String apiKey,
            @Value("${app.embedding.model:text-embedding-3-small}") String model,
            @Value("${app.embedding.dimensions:1536}") int dimensions) {
        this.baseUrl = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        this.apiKey = apiKey;
        this.model = model;
        this.dimensions = dimensions;
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
    }

    @Override
    public String name() {
        return "openai_compatible";
    }

    @Override
    public int dimension() {
        return dimensions;
    }

    @Override
    public List<Double> embed(String text) {
        return embedBatch(List.of(text)).get(0);
    }

    @Override
    public List<List<Double>> embedBatch(List<String> texts) {
        if (texts.isEmpty()) {
            return List.of();
        }
        try {
            List<String> escaped = new ArrayList<>(texts.size());
            for (String t : texts) {
                escaped.add(escapeJson(t));
            }
            String inputs = String.join(", ", escaped);
            // 单条用 "input": "...", 多条用 "input": ["...", "..."]
            String body = texts.size() == 1
                    ? String.format("{\"model\":\"%s\",\"input\":%s}", model, inputs)
                    : String.format("{\"model\":\"%s\",\"input\":[%s]}", model, inputs);

            HttpRequest.Builder rb = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + "/embeddings"))
                    .header("Content-Type", "application/json")
                    .timeout(Duration.ofSeconds(30))
                    .POST(HttpRequest.BodyPublishers.ofString(body));
            if (apiKey != null && !apiKey.isBlank()) {
                rb.header("Authorization", "Bearer " + apiKey);
            }
            HttpRequest request = rb.build();

            HttpResponse<String> resp = http.send(request, HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() != 200) {
                log.warn("embedding_api_error: status={} body={}", resp.statusCode(), resp.body());
                return fallback(texts);
            }
            return parseEmbeddings(resp.body(), texts.size());
        } catch (Exception e) {
            log.warn("embedding_request_failed: {}", e.toString());
            return fallback(texts);
        }
    }

    /**
     * API 不可用时回退到 MockEmbeddingProvider(确定性,无外部依赖)。
     */
    private List<List<Double>> fallback(List<String> texts) {
        MockEmbeddingProvider mock = new MockEmbeddingProvider();
        return mock.embedBatch(texts);
    }

    /**
     * 极简 JSON 嵌入解析: 扫描 "embedding":[ ... ] 数组。
     * 避免引入额外 JSON 依赖,只提取数字。
     */
    private List<List<Double>> parseEmbeddings(String json, int expectedCount) {
        List<List<Double>> result = new ArrayList<>();
        // 找到每个 "embedding":[...]
        int idx = 0;
        while (result.size() < expectedCount) {
            int keyIdx = json.indexOf("\"embedding\"", idx);
            if (keyIdx < 0) break;
            int arrStart = json.indexOf('[', keyIdx + 11);
            if (arrStart < 0) break;
            // 匹配对应 ']'
            int depth = 0;
            int arrEnd = arrStart;
            for (int i = arrStart; i < json.length(); i++) {
                char c = json.charAt(i);
                if (c == '[') depth++;
                else if (c == ']') {
                    depth--;
                    if (depth == 0) {
                        arrEnd = i;
                        break;
                    }
                }
            }
            String arr = json.substring(arrStart + 1, arrEnd);
            List<Double> vec = new ArrayList<>();
            Matcher m = NUMBER.matcher(arr);
            while (m.find()) {
                vec.add(Double.parseDouble(m.group()));
            }
            result.add(vec);
            idx = arrEnd + 1;
        }
        // 解析不足时补零向量
        while (result.size() < expectedCount) {
            List<Double> z = new ArrayList<>(dimensions);
            for (int i = 0; i < dimensions; i++) z.add(0.0);
            result.add(z);
        }
        return result;
    }

    private static String escapeJson(String s) {
        StringBuilder sb = new StringBuilder(s.length() + 10);
        sb.append('"');
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"' -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                default -> {
                    if (c < 0x20) sb.append(String.format("\\u%04x", (int) c));
                    else sb.append(c);
                }
            }
        }
        sb.append('"');
        return sb.toString();
    }

    @SuppressWarnings("unused")
    private Map<String, String> headers() {
        return Map.of("X-Provider", name());
    }
}
