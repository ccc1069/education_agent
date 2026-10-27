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
    name = "review_schedules",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_review_learner_knowledge",
        columnNames = {"learner_id", "knowledge_id"}
    )
)
public class ReviewSchedule {

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

    @Column(name = "easiness_factor", nullable = false)
    private Double easinessFactor = 2.5;

    @Column(name = "interval_days", nullable = false)
    private Double intervalDays = 1.0;

    @Column(name = "repetition", nullable = false)
    private Integer repetition = 0;

    @Column(name = "total_reviews", nullable = false)
    private Integer totalReviews = 0;

    @Column(name = "next_review", nullable = false)
    private Instant nextReview;

    @Column(name = "last_review")
    private Instant lastReview;

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
