package com.edu.agent.db.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
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
@Table(
    name = "privacy_consents",
    indexes = {
        @Index(name = "ix_consent_user_type", columnList = "user_id,consent_type")
    }
)
public class PrivacyConsent {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", columnDefinition = "bigint")
    private BigInteger id;

    @Column(name = "tenant_id", nullable = false)
    private BigInteger tenantId = BigInteger.ONE;

    @Column(name = "user_id", nullable = false)
    private BigInteger userId;

    @Column(name = "consent_type", nullable = false, length = 32)
    private String consentType;

    @Column(name = "granted", nullable = false)
    private Boolean granted;

    @Column(name = "consent_version", nullable = false, length = 16)
    private String consentVersion = "1.0";

    @Column(name = "ip", nullable = false, length = 64)
    private String ip = "";

    @Column(name = "user_agent", nullable = false, length = 256)
    private String userAgent = "";

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;
    @jakarta.persistence.PrePersist
    void onCreate() {
        Instant now = Instant.now();
        if (createdAt == null) createdAt = now;
    }

}
