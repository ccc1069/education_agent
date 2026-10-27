package com.edu.agent.controller;

import com.edu.agent.security.SecurityContextHelper;
import com.edu.agent.service.TaskService;
import jakarta.validation.constraints.Min;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 任务调度路由 -- 对齐 Python /api/v1/admin/tasks/*。
 * 仅平台管理员可访问。
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/admin/tasks")
@RequiredArgsConstructor
public class TaskController {

    private final TaskService taskService;
    private final SecurityContextHelper securityContext;

    @GetMapping
    @PreAuthorize("hasRole('ADMIN')")
    public Map<String, Object> listTasks() {
        return taskService.listTasks();
    }

    @GetMapping("/history")
    @PreAuthorize("hasRole('ADMIN')")
    public List<Map<String, Object>> listHistory(@RequestParam(defaultValue = "50") @Min(1) Integer limit,
                                                  @RequestParam(defaultValue = "0") @Min(0) Integer offset,
                                                  @RequestParam(required = false) String task_name,
                                                  @RequestParam(required = false, name = "status") String statusFilter) {
        return taskService.listHistory(limit, offset, task_name, statusFilter);
    }

    @PostMapping("/trigger/{taskName}")
    @PreAuthorize("hasRole('ADMIN')")
    public Map<String, Object> trigger(@PathVariable String taskName) {
        String triggeredBy = "manual:" + securityContext.require().getEmail();
        return taskService.triggerTask(taskName, triggeredBy);
    }

    @PostMapping("/{taskName}/run")
    @PreAuthorize("hasRole('ADMIN')")
    public Map<String, Object> runSync(@PathVariable String taskName) {
        String triggeredBy = "manual:" + securityContext.require().getEmail();
        return taskService.triggerTask(taskName, triggeredBy);
    }

    @GetMapping("/queue/stats")
    @PreAuthorize("hasRole('ADMIN')")
    public Map<String, Object> queueStats() {
        return taskService.queueStats();
    }

    @GetMapping("/queue/dead-letters")
    @PreAuthorize("hasRole('ADMIN')")
    public List<Map<String, Object>> deadLetters() {
        return List.of();
    }
}
