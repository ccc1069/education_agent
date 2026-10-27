package com.edu.agent.db.repository;

import com.edu.agent.db.entity.KnowledgePrerequisite;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.util.List;

@Repository
public interface KnowledgePrerequisiteRepository
        extends JpaRepository<KnowledgePrerequisite, KnowledgePrerequisite.PK> {

    @Query("SELECT p.prerequisiteId FROM KnowledgePrerequisite p WHERE p.nodeId = :nodeId")
    List<BigInteger> findPrerequisitesByNodeId(BigInteger nodeId);

    void deleteByNodeId(BigInteger nodeId);
}
