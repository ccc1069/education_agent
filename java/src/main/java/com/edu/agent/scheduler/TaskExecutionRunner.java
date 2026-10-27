package com.edu.agent.scheduler;

import com.edu.agent.db.entity.TaskExecution;
import com.edu.agent.db.repository.TaskExecutionRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigInteger;
import java.time.Instant;
import java.util.Map;
import java.util.function.Supplier;

/**
 * 定时任务执行器 -- 对齐 Python SchedulerService._enqueue_with_history。
 *
 * <p>封装"写 running 记录 -> 执行 -> 写回结果"的状态机,供所有定时任务共用。
 * 每次执行都持久化到 task_executions 表,供管理员查看历史。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class TaskExecutionRunner {

    private final TaskExecutionRepository repository;

    /**
     * 执行任务并记录历史。
     *
     * @param taskName    任务名
     * @param triggeredBy 触发来源(scheduler / manual)
     * @param job         任务逻辑(返回 metadata map)
     * @return 执行结果(status/duration_ms/error)
     */
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public Map<String, Object> run(String taskName, String triggeredBy, Supplier<Map<String, Object>> job) {
        TaskExecution execution = new TaskExecution();
        execution.setTaskName(taskName);
        execution.setStatus("running");
        execution.setTriggeredBy(triggeredBy);
        execution = repository.saveAndFlush(execution);
        BigInteger execId = execution.getId();

        Instant start = Instant.now();
        String error = null;
        String status = "success";
        Map<String, Object> meta = Map.of();

        try {
            meta = job.get();
            if (meta == null) meta = Map.of();
        } catch (Exception e) {
            status = "failed";
            error = e.getClass().getSimpleName() + ": " + e.getMessage();
            log.error("scheduled_task_failed: name={} err={}", taskName, error);
        }

        Instant completed = Instant.now();
        long durationMs = completed.toEpochMilli() - start.toEpochMilli();
        execution.setStatus(status);
        execution.setCompletedAt(completed);
        execution.setDurationMs((int) Math.min(durationMs, Integer.MAX_VALUE));
        execution.setErrorMessage(error);
        execution.setMetadata(meta);
        repository.save(execution);

        log.info("task_executed: name={} status={} duration_ms={}", taskName, status, durationMs);
        return Map.of(
                "id", execId,
                "name", taskName,
                "status", status,
                "duration_ms", durationMs,
                "error", error
        );
    }
}
