package com.edu.agent.db.repository;

import com.edu.agent.db.entity.ReviewSchedule;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

@Repository
public interface ReviewScheduleRepository extends JpaRepository<ReviewSchedule, BigInteger> {
    Optional<ReviewSchedule> findByLearnerIdAndKnowledgeId(BigInteger learnerId, String knowledgeId);
    List<ReviewSchedule> findByLearnerId(BigInteger learnerId);
    List<ReviewSchedule> findByNextReviewBefore(Instant before);
}
