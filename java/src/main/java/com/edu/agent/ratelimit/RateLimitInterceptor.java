package com.edu.agent.ratelimit;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedDeque;

/**
 * 滑动窗口限流拦截器 -- 对齐 Python core/rate_limiter.py。
 *
 * 双维度限流:
 *   1. 全局每 IP: 默认 100/min(global)
 *   2. 端点级: login/register/refresh 各有独立配额
 *
 * 内存实现(生产可换 Redis):ConcurrentHashMap<key, Deque<timestamp>>,
 *   每次请求清理过期时间戳,若剩余 >= limit 则拒绝。
 *
 * 返回头: X-RateLimit-Limit / X-RateLimit-Remaining / X-RateLimit-Reset / Retry-After
 */
@Slf4j
@Component
public class RateLimitInterceptor implements HandlerInterceptor {

    @Value("${app.rate-limit.enabled:true}")
    private boolean enabled;

    @Value("${app.rate-limit.global-per-min:100}")
    private int globalPerMin;

    @Value("${app.rate-limit.login-per-min:5}")
    private int loginPerMin;

    @Value("${app.rate-limit.register-per-min:3}")
    private int registerPerMin;

    @Value("${app.rate-limit.refresh-per-min:10}")
    private int refreshPerMin;

    private final Map<String, Deque<Long>> buckets = new ConcurrentHashMap<>();

    @Override
    public boolean preHandle(HttpServletRequest req, HttpServletResponse resp, Object handler) {
        if (!enabled) return true;
        String path = req.getRequestURI();
        String ip = clientIp(req);
        String bucket = bucketFor(path, ip);
        int limit = limitFor(path);

        long now = Instant.now().toEpochMilli();
        long windowStart = now - 60_000L;
        Deque<Long> timestamps = buckets.computeIfAbsent(bucket, k -> new ConcurrentLinkedDeque<>());
        synchronized (timestamps) {
            // 清理过期
            while (!timestamps.isEmpty() && timestamps.peekFirst() < windowStart) {
                timestamps.pollFirst();
            }
            if (timestamps.size() >= limit) {
                long resetAt = (timestamps.peekFirst() != null ? timestamps.peekFirst() : now) + 60_000L;
                resp.setHeader("X-RateLimit-Limit", String.valueOf(limit));
                resp.setHeader("X-RateLimit-Remaining", "0");
                resp.setHeader("X-RateLimit-Reset", String.valueOf(Math.max(0, (resetAt - now) / 1000)));
                resp.setHeader("Retry-After", String.valueOf(Math.max(1, (resetAt - now) / 1000)));
                resp.setStatus(429);
                log.warn("rate_limited: bucket={} path={} ip={}", bucket, path, ip);
                return false;
            }
            timestamps.addLast(now);
            int remaining = limit - timestamps.size();
            long resetIn = 60;
            resp.setHeader("X-RateLimit-Limit", String.valueOf(limit));
            resp.setHeader("X-RateLimit-Remaining", String.valueOf(Math.max(0, remaining)));
            resp.setHeader("X-RateLimit-Reset", String.valueOf(resetIn));
        }
        return true;
    }

    private int limitFor(String path) {
        if (path.endsWith("/auth/login")) return loginPerMin;
        if (path.endsWith("/auth/register")) return registerPerMin;
        if (path.endsWith("/auth/refresh")) return refreshPerMin;
        return globalPerMin;
    }

    private String bucketFor(String path, String ip) {
        if (path.endsWith("/auth/login")) return "login:" + ip;
        if (path.endsWith("/auth/register")) return "register:" + ip;
        if (path.endsWith("/auth/refresh")) return "refresh:" + ip;
        return "global:" + ip;
    }

    private String clientIp(HttpServletRequest req) {
        String xff = req.getHeader("X-Forwarded-For");
        if (xff != null && !xff.isBlank()) return xff.split(",")[0].trim();
        return req.getRemoteAddr();
    }

    /** 测试用: 清空所有桶。 */
    public void resetForTest() {
        buckets.clear();
    }

    /** 测试用: 取某桶当前已用次数。 */
    public int currentCount(String bucket) {
        Deque<Long> ts = buckets.get(bucket);
        if (ts == null) return 0;
        synchronized (ts) {
            long windowStart = Instant.now().toEpochMilli() - 60_000L;
            List<Long> keep = new ArrayList<>();
            for (Long t : ts) if (t >= windowStart) keep.add(t);
            return keep.size();
        }
    }
}
