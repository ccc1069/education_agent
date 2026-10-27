package com.edu.agent.service;

import com.edu.agent.core.LearnerModel;
import com.edu.agent.db.entity.KnowledgeState;
import com.edu.agent.db.entity.Learner;
import com.edu.agent.db.entity.Submission;
import com.edu.agent.db.repository.KnowledgeStateRepository;
import com.edu.agent.db.repository.LearnerRepository;
import com.edu.agent.db.repository.SubmissionRepository;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigInteger;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 学习者模型 L1 缓存 + L2 DB 写回，对齐 Python LearnerModelService。
 * <p>
 * knowledge_states 使用 CAS（WHERE version=?）；冲突时使缓存失效并抛错，由调用方重试。
 */
@Slf4j
@Service
public class LearnerModelService {

    public static class OptimisticLockException extends RuntimeException {
        public OptimisticLockException(String message) {
            super(message);
        }
    }

    private static final int CAS_MAX_RETRIES = 3;

    private final LearnerRepository learnerRepository;
    private final KnowledgeStateRepository knowledgeStateRepository;
    private final SubmissionRepository submissionRepository;
    private final Map<String, LearnerModel> cache = new ConcurrentHashMap<>();
    private final Map<String, BigInteger> idMap = new ConcurrentHashMap<>();
    private final boolean inMemoryOnly;

    public LearnerModelService(LearnerRepository learnerRepository,
                               KnowledgeStateRepository knowledgeStateRepository,
                               SubmissionRepository submissionRepository) {
        this.learnerRepository = learnerRepository;
        this.knowledgeStateRepository = knowledgeStateRepository;
        this.submissionRepository = submissionRepository;
        this.inMemoryOnly = false;
    }

    public static LearnerModelService inMemoryOnly() {
        return new LearnerModelService(true);
    }

    private LearnerModelService(boolean inMemoryOnly) {
        this.learnerRepository = null;
        this.knowledgeStateRepository = null;
        this.submissionRepository = null;
        this.inMemoryOnly = inMemoryOnly;
    }

    public Map<String, LearnerModel> getCache() {
        return cache;
    }

    public void invalidate(String learnerPublicId) {
        cache.remove(learnerPublicId);
        idMap.remove(learnerPublicId);
    }

    @Transactional
    public LearnerModel getOrLoad(String learnerPublicId) {
        LearnerModel cached = cache.get(learnerPublicId);
        if (cached != null) {
            return cached;
        }
        if (inMemoryOnly) {
            LearnerModel model = new LearnerModel(learnerPublicId);
            cache.put(learnerPublicId, model);
            return model;
        }

        Learner learner = learnerRepository.findByPublicId(learnerPublicId)
                .orElseGet(() -> createLearner(learnerPublicId));
        List<KnowledgeState> rows = knowledgeStateRepository.findByLearnerId(learner.getId());

        LearnerModel model = new LearnerModel(learnerPublicId);
        for (KnowledgeState row : rows) {
            LearnerModel.KnowledgeState state = new LearnerModel.KnowledgeState(
                    row.getKnowledgeId(), row.getMastery() != null ? row.getMastery() : 0.1);
            if (row.getAttempts() != null) state.setAttempts(row.getAttempts());
            if (row.getCorrectCount() != null) state.setCorrectCount(row.getCorrectCount());
            if (row.getStreak() != null) state.setStreak(row.getStreak());
            if (row.getLastAttempt() != null) state.setLastAttempt(row.getLastAttempt());
            if (row.getVersion() != null) state.setVersion(row.getVersion());
            model.putState(state);
        }
        cache.put(learnerPublicId, model);
        idMap.put(learnerPublicId, learner.getId());
        log.info("Loaded learner model from DB: {} (states={})", learnerPublicId, rows.size());
        return model;
    }

    @Transactional
    public void recordSubmission(String learnerPublicId, String knowledgeId,
                                 boolean isCorrect, double timeSpentSeconds) {
        if (inMemoryOnly) {
            return;
        }
        Learner learner = resolveLearner(learnerPublicId);
        Submission sub = new Submission();
        sub.setTenantId(learner.getTenantId() != null ? learner.getTenantId() : BigInteger.ONE);
        sub.setLearnerId(learner.getId());
        sub.setKnowledgeId(knowledgeId);
        sub.setIsCorrect(isCorrect);
        sub.setTimeSpentSeconds(timeSpentSeconds);
        submissionRepository.save(sub);
    }

    @Transactional
    public void save(String learnerPublicId) {
        if (inMemoryOnly) {
            return;
        }
        LearnerModel model = cache.get(learnerPublicId);
        if (model == null) {
            return;
        }
        Learner learner = resolveLearner(learnerPublicId);
        BigInteger internalId = learner.getId();
        BigInteger tenantId = learner.getTenantId() != null ? learner.getTenantId() : BigInteger.ONE;
        Instant now = Instant.now();

        for (var entry : model.getStatesView().entrySet()) {
            casSaveState(internalId, tenantId, entry.getValue(), now);
        }
        log.debug("Saved learner model (CAS): {} (states={})", learnerPublicId, model.getStatesView().size());
    }

    private void casSaveState(BigInteger internalId, BigInteger tenantId,
                              LearnerModel.KnowledgeState domain, Instant now) {
        for (int attempt = 1; attempt <= CAS_MAX_RETRIES; attempt++) {
            var existing = knowledgeStateRepository
                    .findByLearnerIdAndKnowledgeId(internalId, domain.getKnowledgeId());
            if (existing.isEmpty()) {
                KnowledgeState row = new KnowledgeState();
                row.setLearnerId(internalId);
                row.setKnowledgeId(domain.getKnowledgeId());
                row.setTenantId(tenantId);
                row.setMastery(domain.getMastery());
                row.setAttempts(domain.getAttempts());
                row.setCorrectCount(domain.getCorrectCount());
                row.setStreak(domain.getStreak());
                row.setLastAttempt(domain.getLastAttempt());
                row.setVersion(1);
                row.setUpdatedAt(now);
                try {
                    knowledgeStateRepository.save(row);
                    domain.setVersion(1);
                    return;
                } catch (RuntimeException e) {
                    // 并发插入：下一轮走 CAS 更新
                    log.debug("insert race kp={}, retry", domain.getKnowledgeId());
                    continue;
                }
            }

            int expected = domain.getVersion() > 0
                    ? domain.getVersion()
                    : (existing.get().getVersion() != null ? existing.get().getVersion() : 1);
            int updated = knowledgeStateRepository.casUpdate(
                    internalId,
                    domain.getKnowledgeId(),
                    expected,
                    domain.getMastery(),
                    domain.getAttempts(),
                    domain.getCorrectCount(),
                    domain.getStreak(),
                    domain.getLastAttempt(),
                    now
            );
            if (updated > 0) {
                domain.setVersion(expected + 1);
                return;
            }
            // 刷新 expected，保留当前请求算出的 mastery（后写覆盖）
            KnowledgeState fresh = knowledgeStateRepository
                    .findByLearnerIdAndKnowledgeId(internalId, domain.getKnowledgeId())
                    .orElseThrow();
            domain.setVersion(fresh.getVersion() != null ? fresh.getVersion() : 0);
            log.warn("CAS conflict kp={} expected={} dbVersion={} attempt={}",
                    domain.getKnowledgeId(), expected, fresh.getVersion(), attempt);
        }
        throw new OptimisticLockException(
                "knowledge_states CAS failed after retries: kp=" + domain.getKnowledgeId());
    }

    private Learner resolveLearner(String learnerPublicId) {
        BigInteger internalId = idMap.get(learnerPublicId);
        if (internalId != null) {
            return learnerRepository.findById(internalId)
                    .orElseGet(() -> {
                        Learner created = createLearner(learnerPublicId);
                        idMap.put(learnerPublicId, created.getId());
                        return created;
                    });
        }
        Learner learner = learnerRepository.findByPublicId(learnerPublicId)
                .orElseGet(() -> createLearner(learnerPublicId));
        idMap.put(learnerPublicId, learner.getId());
        return learner;
    }

    private Learner createLearner(String publicId) {
        Learner learner = new Learner();
        learner.setTenantId(BigInteger.ONE);
        learner.setPublicId(publicId != null && !publicId.isBlank() ? publicId : UUID.randomUUID().toString());
        learner.setName("");
        return learnerRepository.save(learner);
    }
}
