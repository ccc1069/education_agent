package com.edu.agent.db.repository;

import com.edu.agent.db.entity.TenantQuota;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.util.Optional;

@Repository
public interface TenantQuotaRepository extends JpaRepository<TenantQuota, BigInteger> {
    Optional<TenantQuota> findByTenantId(BigInteger tenantId);
}
