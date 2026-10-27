package com.edu.agent.service;

import com.edu.agent.db.entity.TaskExecution;
import com.edu.agent.db.repository.TaskExecutionRepository;
import com.edu.agent.scheduler.ConcreteTasks;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigInteger;
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 任务调度服务 -- 对齐 Python services/task_service.py + core/scheduler.py。
 *
 * <p>提供:
 * <ul>
 *   <li>任务注册表查询</li>
 *   <li>执行历史查询</li>
 *   <li>手动触发(调用 ConcreteTasks 真实逻辑)</li>
 * </ul>
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class TaskService {

    private final TaskExecutionRepository taskExecutionRepository;
    private final ConcreteTasks concreteTasks;

    private static final Map<String, Map<String, String>> TASK_REGISTRY = Map.of(
            "cleanup_expired_tokens", Map.of("description", "清理过期且已撤销的 refresh_tokens", "category", "maintenance"),
            "generate_daily_stats", Map.of("description", "生成每日学习统计", "category", "analytics")
    );

    @Transactional(readOnly = true)
    public Map<String, Object> listTasks() {
        List<Map<String, Object>> registered = TASK_REGISTRY.entrySet().stream()
                .map(e -> {
                    Map<String, Object> m = new HashMap<>();
                    m.put("name", e.getKey());
                    m.put("description", e.getValue().get("description"));
                    m.put("category", e.getValue().get("category"));
                    return m;
                })
                .toList();
        Map<String, Object> queueStats = new HashMap<>();
        queueStats.put("pending", 0);
        queueStats.put("running", 0);
        queueStats.put("dead_letters", 0);
        return Map.of("registered", registered, "queue_stats", queueStats);
    }

    @Transactional(readOnly = true)
    public List<Map<String, Object>> listHistory(int limit, int offset, String taskName, String status) {
        var page = taskExecutionRepository.findAll(
                PageRequest.of(0, Math.max(limit + offset, limit),
                        Sort.by(Sort.Direction.DESC, "startedAt")));
        return page.stream()
                .filter(t -> (taskName == null || taskName.isBlank() || taskName.equals(t.getTaskName()))
                        && (status == null || status.isBlank() || status.equals(t.getStatus())))
                .skip(offset)
                .limit(limit)
                .map(this::toMap)
                .toList();
    }

    @Transactional
    public Map<String, Object> triggerTask(String taskName, String triggeredBy) {
        Instant start = Instant.now();
        return switch (taskName) {
            case "cleanup_expired_tokens" -> {
                var r = concreteTasks.runCleanupNow();
                yield withTiming(r, start);
            }
            case "generate_daily_stats" -> {
                var r = concreteTasks.runDailyStatsNow();
                yield withTiming(r, start);
            }
            default -> throw new IllegalArgumentException(
                    "任务未注册: " + taskName + ", 可用: " + TASK_REGISTRY.keySet());
        };
    }

    @Transactional(readOnly = true)
    public Map<String, Object> queueStats() {
        Map<String, Object> m = new HashMap<>();
        m.put("pending", 0);
        m.put("running", 0);
        m.put("dead_letters", 0);
        return m;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> withTiming(Map<String, Object> result, Instant start) {
        long ms = Duration.between(start, Instant.now()).toMillis();
        Map<String, Object> out = new HashMap<>(result);
        out.put("duration_ms", ms);
        return out;
    }

    private Map<String, Object> toMap(TaskExecution t) {
        Map<String, Object> m = new HashMap<>();
        m.put("id", t.getId());
        m.put("task_name", t.getTaskName());
        m.put("status", t.getStatus());
        m.put("started_at", t.getStartedAt() != null ? t.getStartedAt().toString() : null);
        m.put("completed_at", t.getCompletedAt() != null ? t.getCompletedAt().toString() : null);
        m.put("duration_ms", t.getDurationMs());
        m.put("error_message", t.getErrorMessage());
        m.put("metadata", t.getMetadata());
        m.put("triggered_by", t.getTriggeredBy());
        return m;
    }
}
