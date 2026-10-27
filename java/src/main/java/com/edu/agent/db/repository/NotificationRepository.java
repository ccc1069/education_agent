package com.edu.agent.db.repository;

import com.edu.agent.db.entity.Notification;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.time.Instant;
import java.util.List;

@Repository
public interface NotificationRepository extends JpaRepository<Notification, BigInteger> {
    Page<Notification> findByUserIdOrderByCreatedAtDesc(BigInteger userId, Pageable pageable);
    List<Notification> findByUserIdAndStatus(BigInteger userId, String status);

    long countByUserIdAndStatus(BigInteger userId, String status);

    @Modifying
    @Query("UPDATE Notification n SET n.status = :status, n.readAt = :readAt WHERE n.id = :id")
    int updateStatus(BigInteger id, String status, Instant readAt);
}
