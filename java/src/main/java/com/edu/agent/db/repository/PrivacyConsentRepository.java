package com.edu.agent.db.repository;

import com.edu.agent.db.entity.PrivacyConsent;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.util.List;
import java.util.Optional;

@Repository
public interface PrivacyConsentRepository extends JpaRepository<PrivacyConsent, BigInteger> {
    List<PrivacyConsent> findByUserIdOrderByCreatedAtDesc(BigInteger userId);
    Optional<PrivacyConsent> findFirstByUserIdAndConsentTypeOrderByCreatedAtDesc(BigInteger userId, String consentType);
}
