package com.edu.agent.controller;

import com.edu.agent.db.entity.Notification;
import com.edu.agent.db.entity.NotificationPreference;
import com.edu.agent.security.PrincipalUser;
import com.edu.agent.security.SecurityContextHelper;
import com.edu.agent.service.NotificationService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.math.BigInteger;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 通知路由 -- 对齐 Python /api/v1/notifications/*。
 * 用户只能操作自己的通知。
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/notifications")
@RequiredArgsConstructor
public class NotificationController {

    private final NotificationService notificationService;
    private final SecurityContextHelper securityContext;

    public record NotificationPreferencesRequest(
            Boolean ws_enabled,
            Boolean email_enabled,
            Boolean push_enabled,
            @Min(0) @Max(23) Short quiet_hours_start,
            @Min(0) @Max(23) Short quiet_hours_end,
            @Min(0) @Max(2) Integer min_priority
    ) {}

    @GetMapping
    public Map<String, Object> list(@RequestParam(defaultValue = "20") int limit,
                                    @RequestParam(defaultValue = "0") int offset,
                                    @RequestParam(defaultValue = "false") boolean unread_only) {
        BigInteger userId = securityContext.requireUserId();
        List<Notification> items = notificationService.listNotifications(userId, limit, offset, unread_only);
        long unread = notificationService.countUnread(userId);
        return Map.of(
                "success", true,
                "data", Map.of(
                        "items", items.stream().map(this::toMap).toList(),
                        "total_unread", unread,
                        "limit", limit,
                        "offset", offset
                )
        );
    }

    @GetMapping("/unread-count")
    public Map<String, Object> unreadCount() {
        BigInteger userId = securityContext.requireUserId();
        return Map.of(
                "success", true,
                "data", Map.of("unread", notificationService.countUnread(userId))
        );
    }

    @PostMapping("/read-all")
    public Map<String, Object> markAllRead() {
        BigInteger userId = securityContext.requireUserId();
        int marked = notificationService.markAllRead(userId);
        return Map.of(
                "success", true,
                "data", Map.of("ok", true, "marked", marked)
        );
    }

    @PostMapping("/{notificationId}/read")
    public Map<String, Object> markRead(@PathVariable BigInteger notificationId) {
        BigInteger userId = securityContext.requireUserId();
        boolean ok = notificationService.markRead(notificationId, userId);
        if (!ok) {
            return Map.of("success", false, "error", "NOT_FOUND");
        }
        return Map.of("success", true, "data", Map.of("ok", true, "id", notificationId));
    }

    @GetMapping("/preferences")
    public Map<String, Object> getPreferences() {
        BigInteger userId = securityContext.requireUserId();
        NotificationPreference pref = notificationService.getOrCreatePreferences(userId);
        return Map.of("success", true, "data", toPrefMap(pref));
    }

    @PostMapping("/preferences")
    public Map<String, Object> updatePreferences(@Valid @RequestBody NotificationPreferencesRequest req) {
        BigInteger userId = securityContext.requireUserId();
        NotificationPreference pref = notificationService.updatePreferences(
                userId,
                req.ws_enabled(),
                req.email_enabled(),
                req.push_enabled(),
                req.quiet_hours_start(),
                req.quiet_hours_end(),
                req.min_priority()
        );
        return Map.of("success", true, "data", toPrefMap(pref));
    }

    private Map<String, Object> toMap(Notification n) {
        Map<String, Object> m = new HashMap<>();
        m.put("id", n.getId());
        m.put("type", n.getType());
        m.put("channel", n.getChannel());
        m.put("status", n.getStatus());
        m.put("priority", n.getPriority());
        m.put("title", n.getTitle());
        m.put("body", n.getBody());
        m.put("payload", n.getPayload());
        m.put("created_at", n.getCreatedAt() != null ? n.getCreatedAt().toString() : null);
        m.put("read_at", n.getReadAt() != null ? n.getReadAt().toString() : null);
        return m;
    }

    private Map<String, Object> toPrefMap(NotificationPreference p) {
        Map<String, Object> m = new HashMap<>();
        m.put("ws_enabled", p.getWsEnabled());
        m.put("email_enabled", p.getEmailEnabled());
        m.put("push_enabled", p.getPushEnabled());
        m.put("quiet_hours_start", p.getQuietHoursStart());
        m.put("quiet_hours_end", p.getQuietHoursEnd());
        m.put("min_priority", p.getMinPriority());
        return m;
    }
}
