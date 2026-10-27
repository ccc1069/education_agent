package com.edu.agent.controller;

import com.edu.agent.security.SecurityContextHelper;
import com.edu.agent.service.AuditService;
import jakarta.validation.constraints.Min;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.math.BigInteger;
import java.util.List;
import java.util.Map;

/**
 * 审计日志路由 -- 对齐 Python /api/v1/audit/*。
 * - GET /logs: 分页查询(可按 actor/action 过滤)
 * - GET /verify: HMAC 链完整性校验
 * 仅平台管理员可访问。
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/audit")
@RequiredArgsConstructor
public class AuditLogController {

    private final AuditService auditService;
    private final SecurityContextHelper securityContext;

    @GetMapping("/logs")
    @PreAuthorize("hasRole('ADMIN')")
    public List<Map<String, Object>> listLogs(@RequestParam(defaultValue = "100") @Min(1) Integer limit,
                                               @RequestParam(defaultValue = "0") @Min(0) Integer offset,
                                               @RequestParam(required = false) String actor,
                                               @RequestParam(required = false) String action) {
        BigInteger tenantId = securityContext.requireTenantId();
        return auditService.listRecent(tenantId, limit, offset, actor, action);
    }

    @GetMapping("/verify")
    @PreAuthorize("hasRole('ADMIN')")
    public Map<String, Object> verifyChain(@RequestParam(defaultValue = "1") @Min(1) BigInteger from_log_id) {
        return auditService.verifyChain(from_log_id);
    }
}