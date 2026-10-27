package com.edu.agent.db.repository;

import com.edu.agent.db.entity.Critique;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.util.List;

@Repository
public interface CritiqueRepository extends JpaRepository<Critique, BigInteger> {
    List<Critique> findByLearnerIdOrderByCreatedAtDesc(String learnerId);
    List<Critique> findByNeedsRegenerationTrue();
    List<Critique> findByTenantId(BigInteger tenantId);
}
