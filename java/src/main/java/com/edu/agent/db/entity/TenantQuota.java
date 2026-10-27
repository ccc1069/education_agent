package com.edu.agent.db.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.Filter;
import lombok.Getter;
import lombok.Setter;

import java.math.BigInteger;
import java.time.Instant;

@Getter
@Setter
@org.hibernate.annotations.Filter(name = "tenantFilter", condition = "tenant_id = :tenantId")
@Entity
@Table(name = "tenant_quotas")
public class TenantQuota {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", columnDefinition = "bigint")
    private BigInteger id;

    @Column(name = "tenant_id", nullable = false, unique = true)
    private BigInteger tenantId;

    @Column(name = "max_users", nullable = false)
    private Integer maxUsers = 100;

    @Column(name = "max_llm_tokens_per_month", nullable = false)
    private Integer maxLlmTokensPerMonth = 100_000;

    @Column(name = "current_llm_tokens", nullable = false)
    private Integer currentLlmTokens = 0;

    @Column(name = "period_start", nullable = false)
    private Instant periodStart;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;
    @jakarta.persistence.PrePersist
    void onCreate() {
        Instant now = Instant.now();
        if (createdAt == null) createdAt = now;
        if (updatedAt == null) updatedAt = now;
        if (periodStart == null) periodStart = now;
    }

    @jakarta.persistence.PreUpdate
    void onUpdate() {
        updatedAt = Instant.now();
    }

}
