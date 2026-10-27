package com.edu.agent.db.repository;

import com.edu.agent.db.entity.Submission;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.time.Instant;
import java.util.List;

@Repository
public interface SubmissionRepository extends JpaRepository<Submission, BigInteger> {
    List<Submission> findByLearnerIdOrderByCreatedAtDesc(BigInteger learnerId);
    List<Submission> findByLearnerIdAndKnowledgeId(BigInteger learnerId, String knowledgeId);
    List<Submission> findByCreatedAtBetween(Instant start, Instant end);
}
