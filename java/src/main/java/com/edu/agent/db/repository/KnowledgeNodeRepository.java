package com.edu.agent.db.repository;

import com.edu.agent.db.entity.KnowledgeNode;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.util.List;
import java.util.Optional;

@Repository
public interface KnowledgeNodeRepository extends JpaRepository<KnowledgeNode, BigInteger> {
    Optional<KnowledgeNode> findByPublicId(String publicId);
    List<KnowledgeNode> findBySubject(String subject);
}
