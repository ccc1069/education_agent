package com.edu.agent.observability;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * HTTP 请求耗时统计 Filter -- 对齐 Python MetricsMiddleware。
 *
 * <p>跳过 /actuator /metrics /health 等监控端点本身,避免自递归噪声。
 * 路径归一化: 把数字 ID 替换为 :id,避免基数爆炸。
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class MetricsFilter extends OncePerRequestFilter {

    private static final java.util.Set<String> SKIP_PATHS = java.util.Set.of(
            "/actuator", "/actuator/health", "/actuator/info", "/actuator/prometheus",
            "/health", "/ready", "/live", "/metrics");

    private final AgentMetrics metrics;

    public MetricsFilter(AgentMetrics metrics) {
        this.metrics = metrics;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String path = request.getRequestURI();
        if (SKIP_PATHS.contains(path)) {
            filterChain.doFilter(request, response);
            return;
        }

        long start = System.currentTimeMillis();
        try {
            filterChain.doFilter(request, response);
        } finally {
            long duration = System.currentTimeMillis() - start;
            String normalizedPath = normalizePath(path);
            metrics.recordHttpRequest(request.getMethod(), normalizedPath, response.getStatus(), duration);
        }
    }

    /**
     * 路径归一化 -- 把 /api/learners/123/submissions -> /api/learners/:id/submissions。
     */
    static String normalizePath(String path) {
        if (path == null || path.isEmpty()) return "/";
        String[] parts = path.split("/");
        StringBuilder sb = new StringBuilder();
        for (String p : parts) {
            if (p.isEmpty()) continue; // skip leading empty from split
            sb.append("/");
            if (p.matches("\\d+")) {
                sb.append(":id");
            } else if (p.matches("[0-9a-fA-F\\-]{8,}")) {
                // UUID 形式
                sb.append(":id");
            } else {
                sb.append(p);
            }
        }
        return sb.length() > 0 ? sb.toString() : "/";
    }
}
