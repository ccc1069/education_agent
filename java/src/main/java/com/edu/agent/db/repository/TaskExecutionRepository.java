package com.edu.agent.db.repository;

import com.edu.agent.db.entity.TaskExecution;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.time.Instant;
import java.util.List;

@Repository
public interface TaskExecutionRepository extends JpaRepository<TaskExecution, BigInteger> {
    Page<TaskExecution> findByTenantIdOrderByStartedAtDesc(BigInteger tenantId, Pageable pageable);
    List<TaskExecution> findByTaskNameAndStartedAtAfter(String taskName, Instant after);
    List<TaskExecution> findByStatus(String status);
}
