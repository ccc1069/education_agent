package com.edu.agent.core;

import java.time.Instant;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 学习者知识模型 -- BKT 贝叶斯知识追踪。
 * <p>
 * 与Python版逻辑完全一致，Java版使用ConcurrentHashMap保证线程安全。
 */
public class LearnerModel {

    private final String learnerId;
    private final Map<String, KnowledgeState> states = new ConcurrentHashMap<>();

    // BKT 参数
    private static final double P_INIT = 0.1;
    private static final double P_TRANSIT = 0.15;
    private static final double P_GUESS = 0.2;
    private static final double P_SLIP = 0.1;

    public LearnerModel(String learnerId) {
        this.learnerId = learnerId;
    }

    public String getLearnerId() { return learnerId; }

    public KnowledgeState getState(String knowledgeId) {
        return states.computeIfAbsent(knowledgeId,
                k -> new KnowledgeState(k, P_INIT));
    }

    /**
     * BKT 核心算法：更新 mastery。
     * <p>
     * P(L|correct) = P(L)(1-P(S)) / [P(L)(1-P(S)) + (1-P(L))P(G)]
     * P(L|wrong) = P(L)P(S) / [P(L)P(S) + (1-P(L))(1-P(G))]
     * P(L_new) = P(L|obs) + (1 - P(L|obs)) * P(T)
     */
    public KnowledgeState updateMastery(String knowledgeId, boolean isCorrect) {
        KnowledgeState state = getState(knowledgeId);
        double pL = state.getMastery();

        double pObsGivenL, pObsGivenNotL;
        if (isCorrect) {
            pObsGivenL = 1 - P_SLIP;
            pObsGivenNotL = P_GUESS;
            state.incrementCorrect();
        } else {
            pObsGivenL = P_SLIP;
            pObsGivenNotL = 1 - P_GUESS;
            state.resetStreak();
        }

        double pObs = pL * pObsGivenL + (1 - pL) * pObsGivenNotL;
        double pLGivenObs = pObs > 0 ? (pL * pObsGivenL) / pObs : pL;
        double pLNew = pLGivenObs + (1 - pLGivenObs) * P_TRANSIT;

        state.setMastery(Math.max(0.0, Math.min(1.0, pLNew)));
        state.incrementAttempts();
        state.setLastAttempt(Instant.now());
        return state;
    }

    public List<KnowledgeState> getWeakPoints(double threshold) {
        return states.values().stream()
                .filter(s -> s.getMastery() < threshold && s.getAttempts() > 0)
                .sorted(Comparator.comparingDouble(KnowledgeState::getMastery))
                .toList();
    }

    public List<KnowledgeState> getStrongPoints(double threshold) {
        return states.values().stream()
                .filter(s -> s.getMastery() >= threshold && s.getAttempts() > 0)
                .sorted(Comparator.comparingDouble(KnowledgeState::getMastery).reversed())
                .toList();
    }

    public Map<String, KnowledgeState> getStatesView() {
        return Collections.unmodifiableMap(states);
    }

    /** 从持久化层恢复知识点状态（覆盖同 knowledgeId）。 */
    public void putState(KnowledgeState state) {
        states.put(state.getKnowledgeId(), state);
    }

    public Map<String, Object> getOverallProgress() {
        var stateList = new ArrayList<>(states.values());
        if (stateList.isEmpty()) {
            return Map.of("total", 0, "avg_mastery", 0.0);
        }
        double avgMastery = stateList.stream()
                .mapToDouble(KnowledgeState::getMastery).average().orElse(0);
        int totalAttempts = stateList.stream()
                .mapToInt(KnowledgeState::getAttempts).sum();
        return Map.of(
                "total", stateList.size(),
                "avg_mastery", avgMastery,
                "total_attempts", totalAttempts
        );
    }

    public static class KnowledgeState {
        private final String knowledgeId;
        private double mastery;
        private int attempts;
        private int correctCount;
        private int streak;
        private Instant lastAttempt;
        /** 持久化乐观锁版本；未入库为 0。 */
        private int version;

        public KnowledgeState(String knowledgeId, double initialMastery) {
            this.knowledgeId = knowledgeId;
            this.mastery = initialMastery;
        }

        public String getKnowledgeId() { return knowledgeId; }
        public double getMastery() { return mastery; }
        public void setMastery(double mastery) { this.mastery = mastery; }
        public int getAttempts() { return attempts; }
        public void incrementAttempts() { this.attempts++; }
        public int getCorrectCount() { return correctCount; }
        public void incrementCorrect() { this.correctCount++; this.streak++; }
        public int getStreak() { return streak; }
        public void resetStreak() { this.streak = 0; }
        public Instant getLastAttempt() { return lastAttempt; }
        public void setLastAttempt(Instant lastAttempt) { this.lastAttempt = lastAttempt; }
        public void setAttempts(int attempts) { this.attempts = attempts; }
        public void setCorrectCount(int correctCount) { this.correctCount = correctCount; }
        public void setStreak(int streak) { this.streak = streak; }
        public int getVersion() { return version; }
        public void setVersion(int version) { this.version = version; }

        public String getLevel() {
            if (attempts == 0) return "not_started";
            if (mastery < 0.3) return "beginner";
            if (mastery < 0.6) return "developing";
            if (mastery < 0.85) return "proficient";
            return "mastered";
        }
    }
}
