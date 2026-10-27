package com.edu.agent.observability;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;

/**
 * Correlation ID Filter -- 分布式链路追踪。
 *
 * <p>对齐 Python/Go 的 Correlation ID 机制:
 * <ul>
 *   <li>优先读取请求头 X-Correlation-ID</li>
 *   <li>若不存在则自动生成 UUID</li>
 *   <li>注入 MDC (Mapped Diagnostic Context) 用于日志输出</li>
 *   <li>响应头中返回 X-Correlation-ID 便于客户端追踪</li>
 * </ul>
 *
 * <p>面试要点:
 * <ul>
 *   <li>MDC 基于 ThreadLog,需在异步场景下传递</li>
 *   <li>与 OpenTelemetry TraceID 可共存 (不同抽象层)</li>
 * </ul>
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 5) // 在 MetricsFilter 之前
public class CorrelationIdFilter extends OncePerRequestFilter {

    public static final String CORRELATION_ID_HEADER = "X-Correlation-ID";
    public static final String CORRELATION_ID_MDC_KEY = "correlationId";

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String correlationId = request.getHeader(CORRELATION_ID_HEADER);
        if (correlationId == null || correlationId.isBlank()) {
            correlationId = generateCorrelationId();
        }

        // 注入 MDC
        MDC.put(CORRELATION_ID_MDC_KEY, correlationId);

        // 响应头中返回
        response.setHeader(CORRELATION_ID_HEADER, correlationId);

        try {
            filterChain.doFilter(request, response);
        } finally {
            MDC.remove(CORRELATION_ID_MDC_KEY);
        }
    }

    /**
     * 生成 Correlation ID (UUID v4 短格式)
     */
    private String generateCorrelationId() {
        return UUID.randomUUID().toString().replace("-", "").substring(0, 16);
    }
}
