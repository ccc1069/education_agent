package com.edu.agent.service;

import com.edu.agent.db.entity.Notification;
import com.edu.agent.db.entity.NotificationPreference;
import com.edu.agent.db.repository.NotificationPreferenceRepository;
import com.edu.agent.db.repository.NotificationRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigInteger;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

/**
 * 通知服务 -- 对齐 Python services/notification_service.py。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class NotificationService {

    private final NotificationRepository notificationRepository;
    private final NotificationPreferenceRepository preferenceRepository;

    @Transactional(readOnly = true)
    public List<Notification> listNotifications(BigInteger userId, int limit, int offset, boolean unreadOnly) {
        Pageable pageable = PageRequest.of(offset / Math.max(limit, 1), Math.max(limit, 1),
                Sort.by(Sort.Direction.DESC, "createdAt"));
        if (unreadOnly) {
            return notificationRepository.findByUserIdAndStatus(userId, "pending");
        }
        Page<Notification> page = notificationRepository.findByUserIdOrderByCreatedAtDesc(userId, pageable);
        return page.getContent();
    }

    @Transactional(readOnly = true)
    public long countUnread(BigInteger userId) {
        return notificationRepository.countByUserIdAndStatus(userId, "pending");
    }

    @Transactional
    public boolean markRead(BigInteger notificationId, BigInteger userId) {
        Optional<Notification> opt = notificationRepository.findById(notificationId);
        if (opt.isEmpty()) return false;
        Notification n = opt.get();
        if (!n.getUserId().equals(userId)) return false;
        if ("read".equals(n.getStatus())) return false;
        int updated = notificationRepository.updateStatus(notificationId, "read", Instant.now());
        return updated > 0;
    }

    @Transactional
    public int markAllRead(BigInteger userId) {
        List<Notification> unread = notificationRepository.findByUserIdAndStatus(userId, "pending");
        Instant now = Instant.now();
        for (Notification n : unread) {
            notificationRepository.updateStatus(n.getId(), "read", now);
        }
        return unread.size();
    }

    @Transactional
    public NotificationPreference getOrCreatePreferences(BigInteger userId) {
        return preferenceRepository.findByUserId(userId)
                .orElseGet(() -> {
                    NotificationPreference pref = new NotificationPreference();
                    pref.setUserId(userId);
                    pref.setWsEnabled(true);
                    pref.setEmailEnabled(false);
                    pref.setPushEnabled(false);
                    pref.setMinPriority(0);
                    return preferenceRepository.save(pref);
                });
    }

    @Transactional
    public NotificationPreference updatePreferences(BigInteger userId,
                                                     Boolean wsEnabled,
                                                     Boolean emailEnabled,
                                                     Boolean pushEnabled,
                                                     Short quietHoursStart,
                                                     Short quietHoursEnd,
                                                     Integer minPriority) {
        NotificationPreference pref = getOrCreatePreferences(userId);
        if (wsEnabled != null) pref.setWsEnabled(wsEnabled);
        if (emailEnabled != null) pref.setEmailEnabled(emailEnabled);
        if (pushEnabled != null) pref.setPushEnabled(pushEnabled);
        if (quietHoursStart != null) pref.setQuietHoursStart(quietHoursStart);
        if (quietHoursEnd != null) pref.setQuietHoursEnd(quietHoursEnd);
        if (minPriority != null) pref.setMinPriority(minPriority);
        return preferenceRepository.save(pref);
    }
}
