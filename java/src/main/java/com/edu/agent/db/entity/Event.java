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
@Table(
    name = "events",
    indexes = {
        @Index(name = "ix_events_learner_type", columnList = "learner_public_id,type")
    }
)
public class Event {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", columnDefinition = "bigint")
    private BigInteger id;

    @Column(name = "tenant_id", nullable = false)
    private BigInteger tenantId = BigInteger.ONE;

    @Column(name = "public_id", nullable = false, length = 64, unique = true)
    private String publicId;

    @Column(name = "type", nullable = false, length = 64)
    private String type;

    @Column(name = "source", nullable = false, length = 64)
    private String source;

    @Column(name = "learner_public_id", nullable = false, length = 64)
    private String learnerPublicId;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "data", nullable = false, columnDefinition = "jsonb")
    private Map<String, Object> data = new HashMap<>();

    @Column(name = "correlation_id", length = 64)
    private String correlationId;

    @Column(name = "timestamp", nullable = false)
    private Instant timestamp;
}
