package com.edu.agent.db.repository;

import com.edu.agent.db.entity.Event;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.util.List;

@Repository
public interface EventRepository extends JpaRepository<Event, BigInteger> {
    Page<Event> findByLearnerPublicIdOrderByTimestampDesc(String learnerPublicId, Pageable pageable);
    List<Event> findByCorrelationId(String correlationId);
    List<Event> findByTenantId(BigInteger tenantId);
}
