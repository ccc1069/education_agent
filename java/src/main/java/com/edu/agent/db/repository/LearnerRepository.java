package com.edu.agent.db.repository;

import com.edu.agent.db.entity.Learner;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.util.List;
import java.util.Optional;

@Repository
public interface LearnerRepository extends JpaRepository<Learner, BigInteger> {
    Optional<Learner> findByPublicId(String publicId);
    List<Learner> findByTenantId(BigInteger tenantId);
}
