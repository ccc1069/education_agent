package com.edu.agent.db.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.Filter;
import jakarta.persistence.UniqueConstraint;
import lombok.Getter;
import lombok.Setter;

import java.math.BigInteger;
import java.time.Instant;

@Getter
@Setter
@org.hibernate.annotations.Filter(name = "tenantFilter", condition = "tenant_id = :tenantId")
@Entity
@Table(
    name = "knowledge_states",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_state_learner_knowledge",
        columnNames = {"learner_id", "knowledge_id"}
    )
)
public class KnowledgeState {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", columnDefinition = "bigint")
    private BigInteger id;

    @Column(name = "tenant_id", nullable = false)
    private BigInteger tenantId = BigInteger.ONE;

    @Column(name = "learner_id", nullable = false)
    private BigInteger learnerId;

    @Column(name = "knowledge_id", nullable = false, length = 64)
    private String knowledgeId;

    @Column(name = "mastery", nullable = false)
    private Double mastery = 0.0;

    @Column(name = "alpha", nullable = false)
    private Double alpha = 0.1;

    @Column(name = "beta", nullable = false)
    private Double beta = 0.2;

    @Column(name = "attempts", nullable = false)
    private Integer attempts = 0;

    @Column(name = "correct_count", nullable = false)
    private Integer correctCount = 0;

    @Column(name = "streak", nullable = false)
    private Integer streak = 0;

    @Column(name = "last_attempt")
    private Instant lastAttempt;

    @Column(name = "version", nullable = false)
    private Integer version = 1;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;
    @jakarta.persistence.PrePersist
    void onCreate() {
        Instant now = Instant.now();
        if (updatedAt == null) updatedAt = now;
    }

    @jakarta.persistence.PreUpdate
    void onUpdate() {
        updatedAt = Instant.now();
    }

}
