package com.edu.agent.controller;

import com.edu.agent.db.entity.DataExportJob;
import com.edu.agent.db.entity.PrivacyConsent;
import com.edu.agent.db.entity.PrivacyDeletionRequest;
import com.edu.agent.security.SecurityContextHelper;
import com.edu.agent.service.PrivacyService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.math.BigInteger;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 隐私路由 -- 对齐 Python /api/v1/privacy/*。
 * 用户只能操作自己的数据。
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/privacy")
@RequiredArgsConstructor
public class PrivacyController {

    private final PrivacyService privacyService;
    private final SecurityContextHelper securityContext;

    public record SetConsentRequest(@NotBlank String consent_type, Boolean granted) {}
    public record RequestDeletionRequest(@Size(max = 1000) String reason) {}

    @GetMapping("/consent")
    public Map<String, Object> getConsent() {
        BigInteger userId = securityContext.requireUserId();
        return Map.of("success", true, "data", privacyService.getConsentStatus(userId));
    }

    @PostMapping("/consent")
    public Map<String, Object> setConsent(@Valid @RequestBody SetConsentRequest req,
                                          HttpServletRequest httpReq) {
        BigInteger userId = securityContext.requireUserId();
        if (req.granted() == null) {
            throw new IllegalArgumentException("granted 不能为空");
        }
        PrivacyConsent consent = privacyService.setConsent(
                userId, req.consent_type(), req.granted(),
                clientIp(httpReq), httpReq.getHeader("User-Agent"));
        Map<String, Object> data = new HashMap<>();
        data.put("consent_type", consent.getConsentType());
        data.put("granted", consent.getGranted());
        data.put("consent_version", consent.getConsentVersion());
        data.put("created_at", consent.getCreatedAt() != null ? consent.getCreatedAt().toString() : null);
        return Map.of("success", true, "data", data);
    }

    @PostMapping("/export")
    public Map<String, Object> requestExport() {
        BigInteger userId = securityContext.requireUserId();
        DataExportJob job = privacyService.requestExport(userId);
        return Map.of("success", true, "data", toExportMap(job));
    }

    @GetMapping("/export/jobs")
    public Map<String, Object> listExports() {
        BigInteger userId = securityContext.requireUserId();
        List<Map<String, Object>> items = privacyService.listExports(userId).stream()
                .map(this::toExportMap)
                .toList();
        return Map.of("success", true, "data", items);
    }

    @PostMapping("/delete")
    public Map<String, Object> requestDeletion(@Valid @RequestBody(required = false) RequestDeletionRequest req) {
        BigInteger userId = securityContext.requireUserId();
        String reason = req != null ? req.reason() : "";
        PrivacyDeletionRequest r = privacyService.requestDeletion(userId, reason);
        return Map.of("success", true, "data", toDeletionMap(r));
    }

    @GetMapping("/delete")
    public Map<String, Object> getDeletion() {
        BigInteger userId = securityContext.requireUserId();
        List<PrivacyDeletionRequest> items = privacyService.listDeletionRequests(userId);
        if (items.isEmpty()) {
            return Map.of("success", true, "data", Map.of());
        }
        return Map.of("success", true, "data", toDeletionMap(items.get(0)));
    }

    @PostMapping("/delete/cancel")
    public Map<String, Object> cancelDeletion() {
        BigInteger userId = securityContext.requireUserId();
        List<PrivacyDeletionRequest> items = privacyService.listDeletionRequests(userId);
        PrivacyDeletionRequest pending = items.stream()
                .filter(r -> "pending".equals(r.getStatus()))
                .findFirst()
                .orElse(null);
        if (pending == null) {
            return Map.of("success", false, "error", "NOT_FOUND");
        }
        boolean ok = privacyService.cancelDeletion(userId, pending.getId());
        if (!ok) {
            return Map.of("success", false, "error", "NOT_FOUND");
        }
        return Map.of("success", true, "data", Map.of("cancelled", true, "id", pending.getId()));
    }

    private String clientIp(HttpServletRequest req) {
        String xff = req.getHeader("X-Forwarded-For");
        if (xff != null && !xff.isBlank()) return xff.split(",")[0].trim();
        return req.getRemoteAddr();
    }

    private Map<String, Object> toExportMap(DataExportJob job) {
        Map<String, Object> m = new HashMap<>();
        m.put("id", job.getId());
        m.put("user_id", job.getUserId());
        m.put("status", job.getStatus());
        m.put("requested_at", job.getRequestedAt() != null ? job.getRequestedAt().toString() : null);
        m.put("completed_at", job.getCompletedAt() != null ? job.getCompletedAt().toString() : null);
        m.put("download_url", job.getDownloadUrl());
        m.put("file_size_bytes", job.getFileSizeBytes());
        m.put("error_message", job.getErrorMessage());
        return m;
    }

    private Map<String, Object> toDeletionMap(PrivacyDeletionRequest r) {
        Map<String, Object> m = new HashMap<>();
        m.put("id", r.getId());
        m.put("user_id", r.getUserId());
        m.put("status", r.getStatus());
        m.put("requested_at", r.getRequestedAt() != null ? r.getRequestedAt().toString() : null);
        m.put("scheduled_at", r.getScheduledAt() != null ? r.getScheduledAt().toString() : null);
        m.put("completed_at", r.getCompletedAt() != null ? r.getCompletedAt().toString() : null);
        m.put("cancelled_at", r.getCancelledAt() != null ? r.getCancelledAt().toString() : null);
        m.put("reason", r.getReason());
        return m;
    }
}
