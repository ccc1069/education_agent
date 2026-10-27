package com.edu.agent.observability;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

/**
 * Agent 指标定义 -- 对齐 Python observability/metrics.py。
 *
 * <p>定义的核心指标:
 * <ul>
 *   <li>http_request_duration: HTTP 请求耗时</li>
 *   <li>agent_processing_duration: Agent 处理事件耗时</li>
 *   <li>llm_tokens_used: LLM token 消耗</li>
 *   <li>websocket_active_connections: 当前 WebSocket 连接数</li>
 * </ul>
 */
@Component
public class AgentMetrics {

    public static final String HTTP_REQUEST_DURATION = "http_request_duration_seconds";
    public static final String AGENT_PROCESSING_DURATION = "agent_processing_duration_seconds";
    public static final String LLM_TOKENS_USED = "llm_tokens_used_total";
    public static final String LLM_REQUEST_DURATION = "llm_request_duration_seconds";
    public static final String WS_ACTIVE_CONNECTIONS = "websocket_active_connections";

    private final MeterRegistry registry;

    public AgentMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    /** 记录 HTTP 请求耗时。 */
    public void recordHttpRequest(String method, String path, int status, long durationMs) {
        registry.timer(HTTP_REQUEST_DURATION,
                Tags.of("method", method, "path", path, "status", String.valueOf(status)))
                .record(durationMs, java.util.concurrent.TimeUnit.MILLISECONDS);
    }

    /** 记录 Agent 处理事件耗时。 */
    public void recordAgentProcessing(String agentName, String eventType, long durationMs) {
        registry.timer(AGENT_PROCESSING_DURATION,
                Tags.of("agent_name", agentName, "event_type", eventType))
                .record(durationMs, java.util.concurrent.TimeUnit.MILLISECONDS);
    }

    /** 记录 LLM token 消耗。 */
    public void recordLlmTokens(String provider, String model, String kind, long tokens) {
        registry.counter(LLM_TOKENS_USED,
                Tags.of("provider", provider, "model", model, "kind", kind))
                .increment(tokens);
    }

    /** 设置 WebSocket 连接数(Gauge)。 */
    public void setWebSocketConnections(int count) {
        registry.gauge(WS_ACTIVE_CONNECTIONS, count);
    }

    /** 获取 HTTP 请求 Timer(供 Filter 使用)。 */
    public Timer httpTimer(String method, String path, int status) {
        return registry.timer(HTTP_REQUEST_DURATION,
                Tags.of("method", method, "path", path, "status", String.valueOf(status)));
    }

    /** 获取 Agent 处理 Timer。 */
    public Timer agentTimer(String agentName, String eventType) {
        return registry.timer(AGENT_PROCESSING_DURATION,
                Tags.of("agent_name", agentName, "event_type", eventType));
    }

    /** 获取 LLM token Counter。 */
    public Counter llmTokenCounter(String provider, String model, String kind) {
        return registry.counter(LLM_TOKENS_USED,
                Tags.of("provider", provider, "model", model, "kind", kind));
    }
}
