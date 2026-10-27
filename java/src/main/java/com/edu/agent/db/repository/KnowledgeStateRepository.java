package com.edu.agent.db.repository;

import com.edu.agent.db.entity.KnowledgeState;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.math.BigInteger;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

@Repository
public interface KnowledgeStateRepository extends JpaRepository<KnowledgeState, BigInteger> {
    Optional<KnowledgeState> findByLearnerIdAndKnowledgeId(BigInteger learnerId, String knowledgeId);
    List<KnowledgeState> findByLearnerId(BigInteger learnerId);
    List<KnowledgeState> findByTenantId(BigInteger tenantId);

    /**
     * CAS 更新：仅当 DB version 仍为 expectedVersion 时写入，并 version+1。
     * @return 影响行数，0 表示冲突
     */
    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("""
            UPDATE KnowledgeState k SET
              k.mastery = :mastery,
              k.attempts = :attempts,
              k.correctCount = :correctCount,
              k.streak = :streak,
              k.lastAttempt = :lastAttempt,
              k.version = :expectedVersion + 1,
              k.updatedAt = :updatedAt
            WHERE k.learnerId = :learnerId
              AND k.knowledgeId = :knowledgeId
              AND k.version = :expectedVersion
            """)
    int casUpdate(
            @Param("learnerId") BigInteger learnerId,
            @Param("knowledgeId") String knowledgeId,
            @Param("expectedVersion") int expectedVersion,
            @Param("mastery") Double mastery,
            @Param("attempts") Integer attempts,
            @Param("correctCount") Integer correctCount,
            @Param("streak") Integer streak,
            @Param("lastAttempt") Instant lastAttempt,
            @Param("updatedAt") Instant updatedAt
    );
}
