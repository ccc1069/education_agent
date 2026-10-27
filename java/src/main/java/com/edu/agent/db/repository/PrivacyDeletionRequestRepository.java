package com.edu.agent.db.repository;

import com.edu.agent.db.entity.PrivacyDeletionRequest;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.util.List;
import java.util.Optional;

@Repository
public interface PrivacyDeletionRequestRepository extends JpaRepository<PrivacyDeletionRequest, BigInteger> {
    Optional<PrivacyDeletionRequest> findByUserIdAndStatus(BigInteger userId, String status);
    List<PrivacyDeletionRequest> findByStatus(String status);
    List<PrivacyDeletionRequest> findByUserIdOrderByRequestedAtDesc(BigInteger userId);
}
