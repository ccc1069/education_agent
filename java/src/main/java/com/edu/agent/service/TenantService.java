package com.edu.agent.service;

import com.edu.agent.db.entity.Tenant;
import com.edu.agent.db.entity.TenantQuota;
import com.edu.agent.db.repository.TenantQuotaRepository;
import com.edu.agent.db.repository.TenantRepository;
import com.edu.agent.db.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigInteger;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * 租户管理服务 -- 对齐 Python services/tenant_service.py。
 * - CRUD + 配额管理
 * - user_count 自动统计
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class TenantService {

    private final TenantRepository tenantRepository;
    private final TenantQuotaRepository quotaRepository;
    private final UserRepository userRepository;

    @Transactional
    public Map<String, Object> createTenant(String name, String slug, String plan, Map<String, Object> settings) {
        if (tenantRepository.findBySlug(slug).isPresent()) {
            throw new IllegalArgumentException("slug 已存在: " + slug);
        }
        Tenant t = new Tenant();
        t.setName(name);
        t.setSlug(slug);
        t.setPlan(plan != null ? plan : "free");
        t.setIsActive(true);
        t.setSettings(settings != null ? settings : new HashMap<>());
        t = tenantRepository.save(t);

        TenantQuota q = new TenantQuota();
        q.setTenantId(t.getId());
        q.setMaxUsers(100);
        q.setMaxLlmTokensPerMonth(100_000);
        q.setCurrentLlmTokens(0);
        quotaRepository.save(q);

        return toSummaryMap(t, 0, toQuotaMap(q));
    }

    @Transactional(readOnly = true)
    public List<Map<String, Object>> listTenants(int limit, int offset) {
        return tenantRepository.findAll().stream()
                .skip(offset)
                .limit(limit)
                .map(t -> toSummaryMap(t, countUsers(t.getId()), getQuotaMap(t.getId())))
                .toList();
    }

    @Transactional(readOnly = true)
    public Map<String, Object> getTenant(BigInteger id) {
        return tenantRepository.findById(id)
                .map(t -> toDetailMap(t, countUsers(t.getId()), getQuotaMap(t.getId())))
                .orElse(null);
    }

    @Transactional
    public Map<String, Object> updateTenant(BigInteger id, String name, String plan,
                                             Boolean isActive, Map<String, Object> settings) {
        Tenant t = tenantRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("租户不存在"));
        if (name != null) t.setName(name);
        if (plan != null) t.setPlan(plan);
        if (isActive != null) t.setIsActive(isActive);
        if (settings != null) t.setSettings(settings);
        t = tenantRepository.save(t);
        return toSummaryMap(t, countUsers(t.getId()), getQuotaMap(t.getId()));
    }

    @Transactional
    public boolean deleteTenant(BigInteger id) {
        return tenantRepository.findById(id).map(t -> {
            tenantRepository.delete(t);
            quotaRepository.findByTenantId(id).ifPresent(quotaRepository::delete);
            return true;
        }).orElse(false);
    }

    @Transactional
    public Map<String, Object> updateQuota(BigInteger tenantId, Integer maxUsers, Integer maxLlmTokens) {
        TenantQuota q = quotaRepository.findByTenantId(tenantId)
                .orElseGet(() -> {
                    TenantQuota nq = new TenantQuota();
                    nq.setTenantId(tenantId);
                    nq.setCurrentLlmTokens(0);
                    return nq;
                });
        if (maxUsers != null) q.setMaxUsers(maxUsers);
        if (maxLlmTokens != null) q.setMaxLlmTokensPerMonth(maxLlmTokens);
        q = quotaRepository.save(q);
        return toQuotaMap(q);
    }

    @Transactional
    public Map<String, Object> resetQuota(BigInteger tenantId) {
        TenantQuota q = quotaRepository.findByTenantId(tenantId)
                .orElseGet(() -> {
                    TenantQuota nq = new TenantQuota();
                    nq.setTenantId(tenantId);
                    nq.setMaxUsers(100);
                    nq.setMaxLlmTokensPerMonth(100_000);
                    return nq;
                });
        q.setCurrentLlmTokens(0);
        q = quotaRepository.save(q);
        return toQuotaMap(q);
    }

    private long countUsers(BigInteger tenantId) {
        return userRepository.countByTenantId(tenantId);
    }

    private Map<String, Object> getQuotaMap(BigInteger tenantId) {
        return quotaRepository.findByTenantId(tenantId)
                .map(this::toQuotaMap)
                .orElseGet(() -> {
                    Map<String, Object> m = new HashMap<>();
                    m.put("max_users", 100);
                    m.put("max_llm_tokens_per_month", 100_000);
                    m.put("current_llm_tokens", 0);
                    return m;
                });
    }

    private Map<String, Object> toSummaryMap(Tenant t, long userCount, Map<String, Object> quota) {
        Map<String, Object> m = new HashMap<>();
        m.put("id", t.getId());
        m.put("name", t.getName());
        m.put("slug", t.getSlug());
        m.put("plan", t.getPlan());
        m.put("is_active", t.getIsActive());
        m.put("user_count", userCount);
        m.put("quota", quota);
        return m;
    }

    private Map<String, Object> toDetailMap(Tenant t, long userCount, Map<String, Object> quota) {
        Map<String, Object> m = toSummaryMap(t, userCount, quota);
        m.put("settings", t.getSettings());
        m.put("created_at", t.getCreatedAt() != null ? t.getCreatedAt().toString() : null);
        return m;
    }

    private Map<String, Object> toQuotaMap(TenantQuota q) {
        Map<String, Object> m = new HashMap<>();
        m.put("max_users", q.getMaxUsers());
        m.put("max_llm_tokens_per_month", q.getMaxLlmTokensPerMonth());
        m.put("current_llm_tokens", q.getCurrentLlmTokens());
        m.put("period_start", q.getPeriodStart() != null ? q.getPeriodStart().toString() : null);
        return m;
    }
}
