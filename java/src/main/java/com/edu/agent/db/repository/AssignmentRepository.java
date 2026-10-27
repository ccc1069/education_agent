package com.edu.agent.db.repository;

import com.edu.agent.db.entity.Assignment;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.util.List;

@Repository
public interface AssignmentRepository extends JpaRepository<Assignment, BigInteger> {
    List<Assignment> findByClassId(BigInteger classId);
    List<Assignment> findByClassIdAndStatus(BigInteger classId, String status);
    List<Assignment> findByTeacherId(BigInteger teacherId);
    List<Assignment> findByTeacherIdAndStatus(BigInteger teacherId, String status);
    List<Assignment> findByTenantIdAndStatus(BigInteger tenantId, String status);
    List<Assignment> findByTenantId(BigInteger tenantId);
}
