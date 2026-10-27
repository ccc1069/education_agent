package com.edu.agent.db.repository;

import com.edu.agent.db.entity.AuditLog;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.time.Instant;
import java.util.List;

@Repository
public interface AuditLogRepository extends JpaRepository<AuditLog, BigInteger> {
    Page<AuditLog> findByTenantIdOrderByCreatedAtDesc(BigInteger tenantId, Pageable pageable);
    Page<AuditLog> findByTenantIdAndActorOrderByCreatedAtDesc(BigInteger tenantId, String actor, Pageable pageable);
    Page<AuditLog> findByTenantIdAndActionOrderByCreatedAtDesc(BigInteger tenantId, String action, Pageable pageable);
    Page<AuditLog> findByTenantIdAndActorAndActionOrderByCreatedAtDesc(BigInteger tenantId, String actor, String action, Pageable pageable);
    List<AuditLog> findByCreatedAtAfterOrderByCreatedAtAsc(Instant after);
    List<AuditLog> findByIdGreaterThanEqualOrderByIdAsc(BigInteger fromId);
    long countByCurrHash(String currHash);
}
