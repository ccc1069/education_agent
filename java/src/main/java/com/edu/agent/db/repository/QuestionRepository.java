package com.edu.agent.db.repository;

import com.edu.agent.db.entity.Question;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;

@Repository
public interface QuestionRepository extends JpaRepository<Question, BigInteger> {
    Page<Question> findByTenantId(BigInteger tenantId, Pageable pageable);
    Page<Question> findByTenantIdAndStatus(BigInteger tenantId, String status, Pageable pageable);
    Page<Question> findByTenantIdAndKnowledgeId(BigInteger tenantId, String knowledgeId, Pageable pageable);
    Page<Question> findByTenantIdAndStatusAndKnowledgeId(BigInteger tenantId, String status, String knowledgeId, Pageable pageable);
    Page<Question> findByTenantIdAndStatusAndQuestionType(BigInteger tenantId, String status, String questionType, Pageable pageable);
    Page<Question> findByTenantIdAndStatusAndDifficulty(BigInteger tenantId, String status, Integer difficulty, Pageable pageable);
}
