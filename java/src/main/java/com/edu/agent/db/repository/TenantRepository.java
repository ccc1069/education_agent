package com.edu.agent.db.repository;

import com.edu.agent.db.entity.Tenant;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.util.Optional;

@Repository
public interface TenantRepository extends JpaRepository<Tenant, BigInteger> {
    Optional<Tenant> findBySlug(String slug);
}
