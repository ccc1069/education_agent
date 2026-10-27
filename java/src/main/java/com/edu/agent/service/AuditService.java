package com.edu.agent.service;

import com.edu.agent.db.entity.AuditLog;
import com.edu.agent.db.repository.AuditLogRepository;
import jakarta.annotation.PostConstruct;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * 审计日志服务 -- 对齐 Python services/audit_service.py。
 *
 * HMAC 哈希链:
 *   curr_hash = HMAC-SHA256(secret, prev_hash || id || actor || action || target || created_at_iso)
 *   prev_hash = 上一条 log 的 curr_hash(首条为 "")
 *
 * 不可篡改: 修改任一字段 -> 后续所有 hash 校验失败。
 *
 * secret 优先级: AUDIT_HMAC_SECRET > app.jwt.secret > dev fallback。
 */
@Slf4j
@Service
public class AuditService {

    private final AuditLogRepository auditLogRepository;

    @Value("${app.audit.hmac-secret:}")
    private String hmacSecretConfig;

    @Value("${app.jwt.secret:CHANGE_ME_IN_PRODUCTION}")
    private String jwtSecret;

    private byte[] hmacSecret;

    public AuditService(AuditLogRepository auditLogRepository) {
        this.auditLogRepository = auditLogRepository;
    }

    @PostConstruct
    void initSecret() {
        String raw = (hmacSecretConfig != null && !hmacSecretConfig.isBlank())
                ? hmacSecretConfig
                : jwtSecret;
        if (raw == null || raw.isBlank()) {
            raw = "audit-chain-dev-only-not-for-prod";
        }
        hmacSecret = raw.getBytes(StandardCharsets.UTF_8);
    }

    /**
     * 追加一条审计日志(自动接链)。
     * 使用 REQUIRES_NEW 传播:即使业务事务回滚,审计日志仍保留。
     */
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public Map<String, Object> logAction(BigInteger tenantId, String actor, String action,
                                          String target, String ip, String userAgent,
                                          Map<String, Object> metadata) {
        String prevHash = getLastHash(tenantId);
        AuditLog entry = new AuditLog();
        entry.setTenantId(tenantId != null ? tenantId : BigInteger.ONE);
        entry.setActor(actor != null ? actor : "");
        entry.setAction(action != null ? action : "");
        entry.setTarget(target != null ? target : "");
        entry.setIp(ip != null ? ip : "");
        entry.setUserAgent(userAgent != null ? userAgent : "");
        entry.setMetadata(metadata != null ? metadata : new HashMap<>());
        entry.setPrevHash(prevHash);
        entry.setCurrHash("");
        entry = auditLogRepository.save(entry);
        auditLogRepository.flush();

        String currHash = computeHash(entry.getId(), entry.getActor(), entry.getAction(),
                entry.getTarget(), entry.getCreatedAt(), prevHash);
        entry.setCurrHash(currHash);
        auditLogRepository.save(entry);
        log.info("audit_log: id={} actor={} action={} target={}", entry.getId(), actor, action, target);
        return toMap(entry);
    }

    @Transactional(readOnly = true)
    public List<Map<String, Object>> listRecent(BigInteger tenantId, int limit, int offset,
                                                 String actor, String action) {
        Pageable pageable = PageRequest.of(offset / Math.max(limit, 1), limit);
        Page<AuditLog> page;
        boolean hasActor = actor != null && !actor.isBlank();
        boolean hasAction = action != null && !action.isBlank();
        if (hasActor && hasAction) {
            page = auditLogRepository.findByTenantIdAndActorAndActionOrderByCreatedAtDesc(tenantId, actor, action, pageable);
        } else if (hasActor) {
            page = auditLogRepository.findByTenantIdAndActorOrderByCreatedAtDesc(tenantId, actor, pageable);
        } else if (hasAction) {
            page = auditLogRepository.findByTenantIdAndActionOrderByCreatedAtDesc(tenantId, action, pageable);
        } else {
            page = auditLogRepository.findByTenantIdOrderByCreatedAtDesc(tenantId, pageable);
        }
        return page.stream().map(this::toMap).toList();
    }

    /**
     * 验证从 fromLogId 开始的链完整性。
     * 重算每条 hash 与存储值比对,并校验 prev_hash 链式引用。
     */
    @Transactional(readOnly = true)
    public Map<String, Object> verifyChain(BigInteger fromLogId) {
        List<AuditLog> logs = auditLogRepository.findByIdGreaterThanEqualOrderByIdAsc(fromLogId);
        if (logs.isEmpty()) {
            Map<String, Object> m = new HashMap<>();
            m.put("valid", true);
            m.put("checked", 0);
            m.put("broken_at", null);
            return m;
        }
        String prevHash = logs.get(0).getPrevHash();
        for (AuditLog entry : logs) {
            if (!prevHash.equals(entry.getPrevHash())) {
                log.warn("audit_chain_broken: log_id={} prev_hash mismatch", entry.getId());
                Map<String, Object> m = new HashMap<>();
                m.put("valid", false);
                m.put("checked", entry.getId().subtract(fromLogId).intValue());
                m.put("broken_at", entry.getId());
                m.put("reason", "prev_hash mismatch");
                return m;
            }
            String expected = computeHash(entry.getId(), entry.getActor(), entry.getAction(),
                    entry.getTarget(), entry.getCreatedAt(), prevHash);
            if (!MessageDigest.isEqual(expected.getBytes(StandardCharsets.UTF_8),
                    entry.getCurrHash().getBytes(StandardCharsets.UTF_8))) {
                log.warn("audit_chain_broken: log_id={} hash mismatch", entry.getId());
                Map<String, Object> m = new HashMap<>();
                m.put("valid", false);
                m.put("checked", entry.getId().subtract(fromLogId).intValue());
                m.put("broken_at", entry.getId());
                m.put("reason", "curr_hash mismatch");
                return m;
            }
            prevHash = entry.getCurrHash();
        }
        Map<String, Object> m = new HashMap<>();
        m.put("valid", true);
        m.put("checked", logs.size());
        m.put("broken_at", null);
        return m;
    }

    private String getLastHash(BigInteger tenantId) {
        Pageable pageable = PageRequest.of(0, 1);
        Page<AuditLog> last = auditLogRepository.findByTenantIdOrderByCreatedAtDesc(tenantId, pageable);
        Optional<AuditLog> opt = last.stream().findFirst();
        return opt.map(AuditLog::getCurrHash).orElse("");
    }

    /**
     * 计算 HMAC-SHA256(prev_hash || id || actor || action || target || created_at_iso)。
     */
    private String computeHash(BigInteger id, String actor, String action, String target,
                                Instant createdAt, String prevHash) {
        String payload = String.join("|",
                prevHash != null ? prevHash : "",
                id != null ? id.toString() : "",
                actor != null ? actor : "",
                action != null ? action : "",
                target != null ? target : "",
                createdAt != null ? createdAt.toString() : "");
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(hmacSecret, "HmacSHA256"));
            byte[] hash = mac.doFinal(payload.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (byte b : hash) sb.append(String.format("%02x", b));
            return sb.toString();
        } catch (Exception e) {
            throw new IllegalStateException("HMAC 计算失败", e);
        }
    }

    private Map<String, Object> toMap(AuditLog a) {
        Map<String, Object> m = new HashMap<>();
        m.put("id", a.getId());
        m.put("actor", a.getActor());
        m.put("action", a.getAction());
        m.put("target", a.getTarget());
        m.put("ip", a.getIp());
        m.put("user_agent", a.getUserAgent());
        m.put("metadata", a.getMetadata());
        m.put("created_at", a.getCreatedAt() != null ? a.getCreatedAt().toString() : null);
        m.put("prev_hash", a.getPrevHash());
        m.put("curr_hash", a.getCurrHash());
        return m;
    }
}
