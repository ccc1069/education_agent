package com.edu.agent.controller;

import com.edu.agent.security.SecurityContextHelper;
import com.edu.agent.service.TenantService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.math.BigInteger;
import java.util.List;
import java.util.Map;

/**
 * 租户管理路由 -- 对齐 Python /api/v1/tenants/*。
 * 仅平台管理员可访问。
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/tenants")
@RequiredArgsConstructor
public class TenantController {

    private final TenantService tenantService;
    private final SecurityContextHelper securityContext;

    public record CreateTenantRequest(
            @NotBlank @Size(max = 128) String name,
            @NotBlank @Size(min = 2, max = 64) @Pattern(regexp = "^[a-z0-9][a-z0-9-]*$") String slug,
            @Pattern(regexp = "^(free|pro|enterprise)$") String plan,
            Map<String, Object> settings) {}
    public record UpdateTenantRequest(
            @Size(max = 128) String name,
            @Pattern(regexp = "^(free|pro|enterprise)$") String plan,
            Boolean is_active,
            Map<String, Object> settings) {}
    public record UpdateQuotaRequest(@Min(0) Integer max_users, @Min(0) Integer max_llm_tokens_per_month) {}

    @PostMapping
    @PreAuthorize("hasRole('ADMIN')")
    @ResponseStatus(HttpStatus.CREATED)
    public Map<String, Object> create(@Valid @RequestBody CreateTenantRequest req) {
        return tenantService.createTenant(req.name(), req.slug(), req.plan(), req.settings());
    }

    @GetMapping
    @PreAuthorize("hasRole('ADMIN')")
    public List<Map<String, Object>> list(@RequestParam(defaultValue = "100") @Min(1) Integer limit,
                                           @RequestParam(defaultValue = "0") @Min(0) Integer offset) {
        return tenantService.listTenants(limit, offset);
    }

    @GetMapping("/{tenantId}")
    @PreAuthorize("hasRole('ADMIN')")
    public Map<String, Object> get(@PathVariable BigInteger tenantId) {
        Map<String, Object> t = tenantService.getTenant(tenantId);
        if (t == null) throw new IllegalArgumentException("租户不存在");
        return t;
    }

    @PostMapping("/{tenantId}")
    @PreAuthorize("hasRole('ADMIN')")
    public Map<String, Object> update(@PathVariable BigInteger tenantId,
                                       @Valid @RequestBody UpdateTenantRequest req) {
        return tenantService.updateTenant(tenantId, req.name(), req.plan(), req.is_active(), req.settings());
    }

    @PostMapping("/{tenantId}/delete")
    @PreAuthorize("hasRole('ADMIN')")
    public Map<String, Object> delete(@PathVariable BigInteger tenantId) {
        boolean ok = tenantService.deleteTenant(tenantId);
        if (!ok) throw new IllegalArgumentException("租户不存在");
        return Map.of("success", true, "id", tenantId);
    }

    @PostMapping("/{tenantId}/quota")
    @PreAuthorize("hasRole('ADMIN')")
    public Map<String, Object> updateQuota(@PathVariable BigInteger tenantId,
                                            @Valid @RequestBody UpdateQuotaRequest req) {
        return tenantService.updateQuota(tenantId, req.max_users(), req.max_llm_tokens_per_month());
    }

    @PostMapping("/{tenantId}/quota/reset")
    @PreAuthorize("hasRole('ADMIN')")
    public Map<String, Object> resetQuota(@PathVariable BigInteger tenantId) {
        return tenantService.resetQuota(tenantId);
    }
}
