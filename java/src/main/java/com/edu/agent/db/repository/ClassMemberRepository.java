package com.edu.agent.db.repository;

import com.edu.agent.db.entity.ClassMember;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.util.List;
import java.util.Optional;

@Repository
public interface ClassMemberRepository extends JpaRepository<ClassMember, BigInteger> {
    List<ClassMember> findByClassId(BigInteger classId);
    List<ClassMember> findByLearnerId(BigInteger learnerId);
    Optional<ClassMember> findByClassIdAndLearnerId(BigInteger classId, BigInteger learnerId);
    long countByClassId(BigInteger classId);
}
