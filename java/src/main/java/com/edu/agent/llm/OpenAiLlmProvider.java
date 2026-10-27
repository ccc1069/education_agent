package com.edu.agent.llm;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

/**
 * OpenAI 兼容 API Provider -- 对齐 Python llm.openai_provider.OpenAIProvider。
 *
 * <p>支持任意 OpenAI 兼容服务:
 * <ul>
 *   <li>OpenAI 官方: https://api.openai.com/v1</li>
 *   <li>通义千问(DashScope): https://dashscope.aliyuncs.com/compatible-mode/v1</li>
 *   <li>本地 Ollama: http://localhost:11434/v1</li>
 *   <li>vLLM / Together AI 等</li>
 * </ul>
 *
 * <p>使用 Spring 6.1+ RestClient(同步,Agent 方法本身 @Async 已提供异步)。
 */
@Component
public class OpenAiLlmProvider implements LlmProvider {

    private static final Logger log = LoggerFactory.getLogger(OpenAiLlmProvider.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final String apiKey;
    private final String baseUrl;
    private final String defaultModel;
    private final int timeoutSeconds;
    private final RestClient restClient;

    public OpenAiLlmProvider(
            @Value("${app.llm.api-key:}") String apiKey,
            @Value("${app.llm.base-url:https://api.openai.com/v1}") String baseUrl,
            @Value("${app.llm.model:gpt-4o-mini}") String defaultModel,
            @Value("${app.llm.timeout-seconds:30}") int timeoutSeconds) {
        this.apiKey = apiKey;
        this.baseUrl = baseUrl.replaceAll("/$", "");
        this.defaultModel = defaultModel;
        this.timeoutSeconds = timeoutSeconds;
        this.restClient = RestClient.builder()
                .baseUrl(this.baseUrl)
                .build();
    }

    @Override
    public LlmResponse chat(LlmRequest request) {
        if (!isAvailable()) {
            throw new LlmUnavailableException("OpenAI API key 未配置");
        }

        String model = request.model() != null ? request.model() : defaultModel;
        long start = System.currentTimeMillis();

        // 构造请求体
        ObjectNode body = MAPPER.createObjectNode();
        body.put("model", model);
        body.put("temperature", request.temperature());
        body.put("max_tokens", request.maxTokens());
        body.put("stream", false);

        ArrayNode messages = body.putArray("messages");
        for (LlmMessage msg : request.messages()) {
            ObjectNode m = messages.addObject();
            m.put("role", msg.role().value());
            m.put("content", msg.content());
        }

        try {
            String responseBody = restClient.post()
                    .uri("/chat/completions")
                    .header("Authorization", "Bearer " + apiKey)
                    .header("Content-Type", "application/json")
                    .body(body)
                    .retrieve()
                    .body(String.class);

            double latency = System.currentTimeMillis() - start;
            return parseResponse(responseBody, latency);

        } catch (RestClientResponseException e) {
            log.warn("[OpenAiLlmProvider] HTTP error: status={} body={}", e.getStatusCode(), e.getResponseBodyAsString());
            throw new LlmUnavailableException("OpenAI HTTP " + e.getStatusCode(), e);
        } catch (ResourceAccessException e) {
            log.warn("[OpenAiLlmProvider] network error: {}", e.getMessage());
            throw new LlmUnavailableException("OpenAI 网络错误: " + e.getMessage(), e);
        } catch (LlmUnavailableException e) {
            throw e;
        } catch (Exception e) {
            log.warn("[OpenAiLlmProvider] unexpected error: {}", e.getMessage());
            throw new LlmUnavailableException("OpenAI 调用失败: " + e.getMessage(), e);
        }
    }

    /**
     * 解析 OpenAI /chat/completions 响应。
     */
    private LlmResponse parseResponse(String responseBody, double latencyMs) {
        try {
            JsonNode root = MAPPER.readTree(responseBody);
            JsonNode choices = root.path("choices");
            if (choices.isMissingNode() || !choices.isArray() || choices.isEmpty()) {
                throw new LlmUnavailableException("OpenAI 响应无 choices: " + responseBody.substring(0, Math.min(200, responseBody.length())));
            }
            JsonNode choice = choices.get(0);
            String content = choice.path("message").path("content").asText("");
            String finishReason = choice.path("finish_reason").asText("stop");
            String model = root.path("model").asText(defaultModel);

            // usage
            JsonNode usage = root.path("usage");
            int promptTokens = usage.path("prompt_tokens").asInt(0);
            int completionTokens = usage.path("completion_tokens").asInt(0);
            int totalTokens = usage.path("total_tokens").asInt(0);
            if (totalTokens == 0) totalTokens = promptTokens + completionTokens;

            return new LlmResponse(content, model, promptTokens, completionTokens, totalTokens, finishReason, latencyMs);
        } catch (LlmUnavailableException e) {
            throw e;
        } catch (Exception e) {
            throw new LlmUnavailableException("OpenAI 响应解析失败: " + e.getMessage(), e);
        }
    }

    @Override
    public boolean isAvailable() {
        return apiKey != null && !apiKey.isBlank();
    }

    @Override
    public String name() {
        return "openai";
    }
}
