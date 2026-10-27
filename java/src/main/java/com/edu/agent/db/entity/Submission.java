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
    name = "submissions",
    indexes = {
        @Index(name = "ix_submissions_learner_knowledge", columnList = "learner_id,knowledge_id"),
        @Index(name = "ix_submissions_created_at", columnList = "created_at")
    }
)
public class Submission {

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

    @Column(name = "is_correct", nullable = false)
    private Boolean isCorrect;

    @Column(name = "time_spent_seconds", nullable = false)
    private Double timeSpentSeconds = 0.0;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;
    @jakarta.persistence.PrePersist
    void onCreate() {
        Instant now = Instant.now();
        if (createdAt == null) createdAt = now;
    }

}
