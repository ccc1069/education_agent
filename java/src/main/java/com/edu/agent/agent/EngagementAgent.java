package com.edu.agent.agent;

import com.edu.agent.core.AgentEvent;
import com.edu.agent.core.EventType;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Engagement Agent -- 学习状态监测与自适应干预。
 * <p>
 * 6种学习状态：FOCUSED, STRUGGLING, FRUSTRATED, BORED, FATIGUED, IDLE
 * 检测优先级：idle > frustrated > fatigued > bored > struggling > focused
 */
@Component
public class EngagementAgent {

    private static final Logger log = LoggerFactory.getLogger(EngagementAgent.class);

    private static final int IDLE_THRESHOLD_SECONDS = 300;
    private static final int FATIGUE_THRESHOLD_MINUTES = 45;
    private static final double FATIGUE_ACCURACY_THRESHOLD = 0.5;
    private static final double BOREDOM_ACCURACY_THRESHOLD = 0.9;
    private static final int MAX_RECENT_ITEMS = 20;

    private final ApplicationEventPublisher publisher;
    private final Map<String, LearnerEngagement> engagements = new ConcurrentHashMap<>();

    public EngagementAgent(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public enum LearningState {
        FOCUSED, STRUGGLING, FRUSTRATED, BORED, FATIGUED, IDLE
    }

    @EventListener(condition = "#event.type == T(com.edu.agent.core.EventType).STUDENT_SUBMISSION")
    public void trackSubmission(AgentEvent event) {
        var eng = getEngagement(event.getLearnerId());
        boolean isCorrect = (boolean) event.getData().getOrDefault("is_correct", false);
        double timeSpent = ((Number) event.getData().getOrDefault("time_spent_seconds", 0)).doubleValue();

        synchronized (eng) {
            eng.lastActivity = Instant.now();
            eng.totalInteractions++;
            eng.recentResults.add(isCorrect);
            if (eng.recentResults.size() > MAX_RECENT_ITEMS) {
                eng.recentResults.removeFirst();
            }
            eng.recentResponseTimes.add(timeSpent);
            if (eng.recentResponseTimes.size() > MAX_RECENT_ITEMS) {
                eng.recentResponseTimes.removeFirst();
            }

            if (isCorrect) {
                eng.consecutiveCorrect++;
                eng.consecutiveErrors = 0;
            } else {
                eng.consecutiveErrors++;
                eng.consecutiveCorrect = 0;
            }
        }
    }

    @EventListener(condition = "#event.type == T(com.edu.agent.core.EventType).ASSESSMENT_COMPLETE")
    public void analyzeEngagement(AgentEvent event) {
        var eng = getEngagement(event.getLearnerId());
        LearningState previousState;
        LearningState newState;

        synchronized (eng) {
            previousState = eng.state;
            newState = detectState(eng);
            eng.state = newState;
        }

        if (newState == previousState) {
            return;
        }

        switch (newState) {
            case FRUSTRATED -> {
                Map<String, Object> data = Map.of(
                        "alert_type", "frustration",
                        "consecutive_errors", eng.consecutiveErrors,
                        "message", "别灰心！犯错是学习的一部分。"
                );
                publisher.publishEvent(new AgentEvent(this, EventType.ENGAGEMENT_ALERT,
                        "EngagementAgent", event.getLearnerId(), data));
                publisher.publishEvent(new AgentEvent(this, EventType.PACE_ADJUSTMENT,
                        "EngagementAgent", event.getLearnerId(),
                        Map.of("action", "slow_down", "reason", "frustration")));
            }
            case BORED -> {
                Map<String, Object> data = Map.of(
                        "alert_type", "boredom",
                        "message", "你表现非常棒！让我们挑战更难的内容！"
                );
                publisher.publishEvent(new AgentEvent(this, EventType.ENGAGEMENT_ALERT,
                        "EngagementAgent", event.getLearnerId(), data));
                publisher.publishEvent(new AgentEvent(this, EventType.PACE_ADJUSTMENT,
                        "EngagementAgent", event.getLearnerId(),
                        Map.of("action", "speed_up", "reason", "boredom")));
            }
            case FATIGUED -> {
                Map<String, Object> data = Map.of(
                        "type", "fatigue_break",
                        "session_minutes", eng.getSessionDurationMinutes(),
                        "message", String.format("你已经学习了%.0f分钟，建议休息一下！",
                                eng.getSessionDurationMinutes())
                );
                publisher.publishEvent(new AgentEvent(this, EventType.ENCOURAGEMENT,
                        "EngagementAgent", event.getLearnerId(), data));
            }
            case FOCUSED -> {
                if (eng.consecutiveCorrect >= 3 && eng.encouragementCount % 3 == 0) {
                    Map<String, Object> data = Map.of(
                            "message", String.format("连续%d题全对！继续保持！", eng.consecutiveCorrect),
                            "type", "positive_streak"
                    );
                    publisher.publishEvent(new AgentEvent(this, EventType.ENCOURAGEMENT,
                            "EngagementAgent", event.getLearnerId(), data));
                }
                eng.encouragementCount++;
            }
            default -> { /* STRUGGLING, IDLE: no automatic intervention */ }
        }

        log.info("[Engagement] learner={}, state={} -> {}", event.getLearnerId(), previousState, newState);
    }

    private LearningState detectState(LearnerEngagement eng) {
        if (eng.getIdleSeconds() > IDLE_THRESHOLD_SECONDS) return LearningState.IDLE;
        if (eng.consecutiveErrors >= 3) return LearningState.FRUSTRATED;
        if (eng.getSessionDurationMinutes() > FATIGUE_THRESHOLD_MINUTES
                && eng.getRecentAccuracy() < FATIGUE_ACCURACY_THRESHOLD) return LearningState.FATIGUED;
        if (eng.getRecentAccuracy() > BOREDOM_ACCURACY_THRESHOLD
                && eng.consecutiveCorrect >= 5) return LearningState.BORED;
        if (eng.consecutiveErrors >= 1) return LearningState.STRUGGLING;
        return LearningState.FOCUSED;
    }

    private LearnerEngagement getEngagement(String learnerId) {
        return engagements.computeIfAbsent(learnerId, LearnerEngagement::new);
    }

    static class LearnerEngagement {
        final String learnerId;
        Instant sessionStart = Instant.now();
        Instant lastActivity = Instant.now();
        LinkedList<Boolean> recentResults = new LinkedList<>();
        LinkedList<Double> recentResponseTimes = new LinkedList<>();
        int consecutiveErrors = 0;
        int consecutiveCorrect = 0;
        int totalInteractions = 0;
        int encouragementCount = 0;
        LearningState state = LearningState.FOCUSED;

        LearnerEngagement(String learnerId) {
            this.learnerId = learnerId;
        }

        double getSessionDurationMinutes() {
            return Duration.between(sessionStart, Instant.now()).toMillis() / 60000.0;
        }

        double getIdleSeconds() {
            return Duration.between(lastActivity, Instant.now()).toMillis() / 1000.0;
        }

        double getRecentAccuracy() {
            if (recentResults.isEmpty()) return 0.5;
            int window = Math.min(10, recentResults.size());
            long correct = recentResults.subList(recentResults.size() - window, recentResults.size())
                    .stream().filter(b -> b).count();
            return (double) correct / window;
        }

        double getAvgResponseTime() {
            if (recentResponseTimes.isEmpty()) return 0;
            int window = Math.min(10, recentResponseTimes.size());
            return recentResponseTimes.subList(recentResponseTimes.size() - window, recentResponseTimes.size())
                    .stream().mapToDouble(Double::doubleValue).average().orElse(0);
        }
    }
}
