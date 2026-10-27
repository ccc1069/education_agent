package com.edu.agent.db.repository;

import com.edu.agent.db.entity.ClassRoom;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.util.List;
import java.util.Optional;

@Repository
public interface ClassRoomRepository extends JpaRepository<ClassRoom, BigInteger> {
    Optional<ClassRoom> findByInviteCode(String inviteCode);
    List<ClassRoom> findByTeacherId(BigInteger teacherId);
    List<ClassRoom> findByTenantIdAndIsActive(BigInteger tenantId, Boolean isActive);
}
