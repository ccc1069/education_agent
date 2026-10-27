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
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.math.BigInteger;
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;

@Getter
@Setter
@org.hibernate.annotations.Filter(name = "tenantFilter", condition = "tenant_id = :tenantId")
@Entity
@Table(name = "critiques")
public class Critique {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", columnDefinition = "bigint")
    private BigInteger id;

    @Column(name = "learner_id", nullable = false, length = 64)
    private String learnerId;

    @Column(name = "knowledge_id", nullable = false, length = 128)
    private String knowledgeId;

    @Column(name = "teaching_event_id", length = 64)
    private String teachingEventId;

    @Column(name = "overall", nullable = false)
    private Short overall;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "scores", nullable = false, columnDefinition = "jsonb")
    private Map<String, Object> scores = new HashMap<>();

    @Column(name = "critique", nullable = false, columnDefinition = "text")
    private String critique;

    @Column(name = "needs_regeneration", nullable = false)
    private Boolean needsRegeneration = false;

    @Column(name = "regenerated", nullable = false)
    private Boolean regenerated = false;

    @Column(name = "original_response", nullable = false, columnDefinition = "text")
    private String originalResponse;

    @Column(name = "regenerated_response", columnDefinition = "text")
    private String regeneratedResponse;

    @Column(name = "critic_model", length = 64)
    private String criticModel;

    @Column(name = "critic_tokens", nullable = false)
    private Integer criticTokens = 0;

    @Column(name = "tenant_id", nullable = false)
    private BigInteger tenantId = BigInteger.ONE;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;
    @jakarta.persistence.PrePersist
    void onCreate() {
        Instant now = Instant.now();
        if (createdAt == null) createdAt = now;
    }

}
