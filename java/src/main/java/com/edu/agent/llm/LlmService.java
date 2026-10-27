package com.edu.agent.llm;

import com.edu.agent.observability.AgentMetrics;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * LLM 统一入口 -- 重试 + 熔断 + 指标 + 降级(对齐 Python llm.provider.LLMProvider + factory)。
 *
 * <p>核心职责:
 * <ul>
 *   <li>熔断检查:连续失败达阈值则断开一段时间</li>
 *   <li>指数退避重试:默认 3 次(1s/2s/4s)</li>
 *   <li>超时异常不重试(避免拖死)</li>
 *   <li>记录 Micrometer 指标(llm_request_duration_seconds + llm_tokens_used_total)</li>
 * </ul>
 *
 * <p>调用方应捕获 {@link LlmUnavailableException} 并降级到启发式模板。
 */
@Service
public class LlmService {

    private static final Logger log = LoggerFactory.getLogger(LlmService.class);

    private final LlmProviderFactory providerFactory;
    private final AgentMetrics metrics;

    // 配置
    private final int maxRetries;
    private final long retryBackoffMs;
    private final int circuitBreakerThreshold;
    private final long circuitBreakerDurationSec;

    // 熔断状态
    private final AtomicInteger consecutiveFailures = new AtomicInteger(0);
    private volatile Instant circuitOpenUntil;

    public LlmService(
            LlmProviderFactory providerFactory,
            AgentMetrics metrics,
            @Value("${app.llm.max-retries:3}") int maxRetries,
            @Value("${app.llm.retry-backoff-ms:1000}") long retryBackoffMs,
            @Value("${app.llm.circuit-breaker-threshold:5}") int circuitBreakerThreshold,
            @Value("${app.llm.circuit-breaker-duration-sec:60}") long circuitBreakerDurationSec) {
        this.providerFactory = providerFactory;
        this.metrics = metrics;
        this.maxRetries = maxRetries;
        this.retryBackoffMs = retryBackoffMs;
        this.circuitBreakerThreshold = circuitBreakerThreshold;
        this.circuitBreakerDurationSec = circuitBreakerDurationSec;
    }

    /**
     * 同步调用 LLM,带重试与熔断。
     *
     * @throws LlmUnavailableException 调用失败(熔断/重试耗尽/网络错误)
     */
    public LlmResponse chat(LlmRequest request) {
        // 1. 熔断检查
        if (isCircuitOpen()) {
            throw new LlmUnavailableException("LLM 熔断器断开中,剩余 " + remainingCircuitSeconds() + " 秒");
        }

        LlmProvider provider = providerFactory.getProvider();
        int attempts = 0;
        LlmUnavailableException lastException = null;

        while (attempts < maxRetries) {
            attempts++;
            long start = System.currentTimeMillis();
            try {
                LlmResponse response = provider.chat(request);
                double latencyMs = System.currentTimeMillis() - start;

                // 成功:重置失败计数,记录指标
                consecutiveFailures.set(0);
                recordSuccessMetrics(provider.name(), response, latencyMs);
                return response;

            } catch (LlmUnavailableException e) {
                lastException = e;
                double latencyMs = System.currentTimeMillis() - start;
                recordFailureMetrics(provider.name(), latencyMs);

                // 网络/超时异常不重试(避免拖死)
                if (isNonRetryable(e)) {
                    log.warn("[LlmService] 不可重试异常,停止重试: {}", e.getMessage());
                    break;
                }

                log.warn("[LlmService] 第 {}/{} 次调用失败: {}", attempts, maxRetries, e.getMessage());

                // 指数退避(最后一次不等待)
                if (attempts < maxRetries) {
                    sleepBackoff(attempts);
                }
            }
        }

        // 重试耗尽:触发熔断
        int failures = consecutiveFailures.incrementAndGet();
        if (failures >= circuitBreakerThreshold) {
            tripCircuitBreaker();
            log.warn("[LlmService] 连续 {} 次失败,熔断器断开 {} 秒", failures, circuitBreakerDurationSec);
        }

        throw new LlmUnavailableException(
                "LLM 调用失败(重试 " + attempts + " 次): " + (lastException != null ? lastException.getMessage() : "未知错误"),
                lastException);
    }

    /**
     * 异步调用 LLM(供 Agent 方法使用,与 @Async 配合)。
     */
    public CompletableFuture<LlmResponse> chatAsync(LlmRequest request) {
        return CompletableFuture.supplyAsync(() -> chat(request));
    }

    // ==================== 便捷方法(供 5 个服务使用) ====================

    /**
     * 调用 LLM 并返回内容,失败返回 null(调用方降级到启发式)。
     */
    public String chatOrFallback(LlmRequest request) {
        try {
            return chat(request).content();
        } catch (LlmUnavailableException e) {
            log.debug("[LlmService] LLM 不可用,调用方将降级: {}", e.getMessage());
            return null;
        }
    }

    // ==================== 熔断逻辑 ====================

    private boolean isCircuitOpen() {
        Instant openUntil = circuitOpenUntil;
        if (openUntil == null) return false;
        if (Instant.now().isAfter(openUntil)) {
            // 熔断到期,重置
            circuitOpenUntil = null;
            consecutiveFailures.set(0);
            log.info("[LlmService] 熔断器复位");
            return false;
        }
        return true;
    }

    private long remainingCircuitSeconds() {
        Instant openUntil = circuitOpenUntil;
        if (openUntil == null) return 0;
        long remaining = Duration.between(Instant.now(), openUntil).getSeconds();
        return Math.max(0, remaining);
    }

    private void tripCircuitBreaker() {
        circuitOpenUntil = Instant.now().plusSeconds(circuitBreakerDurationSec);
    }

    // ==================== 重试逻辑 ====================

    private boolean isNonRetryable(LlmUnavailableException e) {
        // 网络超时、连接拒绝等不可恢复异常不重试
        String msg = e.getMessage();
        if (msg == null) return false;
        return msg.contains("网络") || msg.contains("timeout") || msg.contains("超时")
                || msg.contains("连接") || msg.contains("Connection");
    }

    private void sleepBackoff(int attempt) {
        long delay = retryBackoffMs * (1L << (attempt - 1)); // 1s, 2s, 4s...
        try {
            Thread.sleep(delay);
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
        }
    }

    // ==================== 指标 ====================

    private void recordSuccessMetrics(String providerName, LlmResponse response, double latencyMs) {
        metrics.recordLlmTokens(providerName, response.model(), "prompt", (long) response.promptTokens());
        metrics.recordLlmTokens(providerName, response.model(), "completion", (long) response.completionTokens());
        metrics.recordLlmTokens(providerName, response.model(), "total", (long) response.totalTokens());
        if (log.isDebugEnabled()) {
            log.debug("[LlmService] LLM 调用成功: provider={} model={} tokens={} latency={}ms",
                    providerName, response.model(), response.totalTokens(), String.format("%.0f", latencyMs));
        }
    }

    private void recordFailureMetrics(String providerName, double latencyMs) {
        metrics.recordLlmTokens(providerName, "error", "total", 0L);
        log.debug("[LlmService] LLM 调用失败: provider={} latency={}ms", providerName, String.format("%.0f", latencyMs));
    }
}
