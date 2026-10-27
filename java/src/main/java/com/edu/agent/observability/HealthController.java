package com.edu.agent.observability;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.sql.DataSource;
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 健康检查端点 -- 对齐 Python observability/health.py。
 *
 * <p>三个端点:
 * <ul>
 *   <li>/live: 进程存活(永远 200)</li>
 *   <li>/ready: 就绪检查(数据库可连通)</li>
 *   <li>/health: 综合健康检查(含详细子状态)</li>
 * </ul>
 */
@Slf4j
@RestController
@RequestMapping
@RequiredArgsConstructor
public class HealthController {

    private final DataSource dataSource;

    @GetMapping("/live")
    public Map<String, Object> liveness() {
        return Map.of("status", "up", "alive", true);
    }

    @GetMapping("/ready")
    public Map<String, Object> readiness() {
        Map<String, Object> result = new LinkedHashMap<>();
        boolean dbUp = checkDatabase();
        result.put("status", dbUp ? "up" : "down");
        result.put("components", Map.of("database", Map.of("status", dbUp ? "up" : "down")));
        return result;
    }

    @GetMapping("/health")
    public Map<String, Object> health() {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
        long uptimeMs = runtime.getUptime();

        boolean dbUp = checkDatabase();

        Map<String, Object> components = new LinkedHashMap<>();
        components.put("database", Map.of("status", dbUp ? "up" : "down"));
        components.put("jvm", Map.of(
                "status", "up",
                "uptime_ms", uptimeMs,
                "heap_mb", Runtime.getRuntime().totalMemory() / 1024 / 1024));

        String overall = dbUp ? "up" : "down";

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", overall);
        result.put("alive", true);
        result.put("components", components);
        return result;
    }

    private boolean checkDatabase() {
        try {
            JdbcTemplate jdbc = new JdbcTemplate(dataSource);
            jdbc.queryForObject("SELECT 1", Integer.class);
            return true;
        } catch (Exception e) {
            log.warn("Health check DB failed: {}", e.getMessage());
            return false;
        }
    }
}
