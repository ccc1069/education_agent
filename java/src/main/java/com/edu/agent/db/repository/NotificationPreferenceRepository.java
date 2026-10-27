package com.edu.agent.db.repository;

import com.edu.agent.db.entity.NotificationPreference;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.util.Optional;

@Repository
public interface NotificationPreferenceRepository extends JpaRepository<NotificationPreference, BigInteger> {
    Optional<NotificationPreference> findByUserId(BigInteger userId);
}
