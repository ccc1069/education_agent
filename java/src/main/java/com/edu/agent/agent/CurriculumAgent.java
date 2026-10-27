package com.edu.agent.agent;

import com.edu.agent.core.AgentEvent;
import com.edu.agent.core.EventType;
import com.edu.agent.core.KnowledgeGraph;
import com.edu.agent.core.SpacedRepetition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Curriculum Agent -- 动态学习路径 + SM-2 间隔重复 + 知识图谱。
 */
@Component
public class CurriculumAgent {

    private static final Logger log = LoggerFactory.getLogger(CurriculumAgent.class);
    private static final double MASTERY_THRESHOLD = 0.6;
    private static final int MAX_DUE_ITEMS = 5;

    private final ApplicationEventPublisher publisher;
    private final SpacedRepetition sr = new SpacedRepetition();
    private final KnowledgeGraph knowledgeGraph = KnowledgeGraph.buildSampleMathGraph();
    private final Map<String, Map<String, SpacedRepetition.ReviewItem>> reviewItems =
            new ConcurrentHashMap<>();

    public CurriculumAgent(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @EventListener(condition = "#event.type == T(com.edu.agent.core.EventType).MASTERY_UPDATED")
    public void handleMasteryUpdate(AgentEvent event) {
        String learnerId = event.getLearnerId();
        String knowledgeId = (String) event.getData().getOrDefault("knowledge_id", "");
        double mastery = ((Number) event.getData().getOrDefault("mastery", 0.0)).doubleValue();

        int quality = masteryToQuality(mastery);
        SpacedRepetition.ReviewItem item = getReviewItem(learnerId, knowledgeId);
        sr.review(item, quality);

        log.info("[Curriculum] learner={}, kp={}, EF={:.2f}, interval={:.1f}d",
                learnerId, knowledgeId, item.getEasinessFactor(), item.getIntervalDays());

        sendReviewSchedule(learnerId, event.getCorrelationId());

        if (mastery >= MASTERY_THRESHOLD) {
            checkAndRecommendNext(learnerId, event.getCorrelationId());
        }
    }

    @EventListener(condition = "#event.type == T(com.edu.agent.core.EventType).WEAKNESS_DETECTED")
    public void handleWeakness(AgentEvent event) {
        String knowledgeId = (String) event.getData().getOrDefault("knowledge_id", "");
        Set<String> masteredIds = getMasteredIds(event.getLearnerId());
        List<String> remedialPath = knowledgeGraph.getLearningPath(knowledgeId, masteredIds);

        Map<String, Object> data = new HashMap<>();
        data.put("reason", "weakness_detected");
        data.put("weak_knowledge_id", knowledgeId);
        data.put("remedial_path", remedialPath);
        data.put("message", "检测到薄弱知识点，建议先复习前置知识");
        publisher.publishEvent(new AgentEvent(this, EventType.PATH_UPDATED,
                "CurriculumAgent", event.getLearnerId(), data, event.getCorrelationId()));
    }

    @EventListener(condition = "#event.type == T(com.edu.agent.core.EventType).PACE_ADJUSTMENT")
    public void handlePaceAdjustment(AgentEvent event) {
        String action = (String) event.getData().getOrDefault("action", "unknown");
        String reason = (String) event.getData().getOrDefault("reason", "");
        log.info("[Curriculum] learner={}, pace_adjustment: action={}, reason={}",
                event.getLearnerId(), action, reason);
    }

    private void sendReviewSchedule(String learnerId, String correlationId) {
        Map<String, SpacedRepetition.ReviewItem> items = reviewItems.get(learnerId);
        if (items == null || items.isEmpty()) return;

        List<SpacedRepetition.ReviewItem> dueItems = sr.getDueItems(items);
        Map<String, List<String>> weeklySchedule = sr.getStudySchedule(items, 7);

        List<Map<String, Object>> dueNow = new ArrayList<>();
        for (int i = 0; i < Math.min(MAX_DUE_ITEMS, dueItems.size()); i++) {
            SpacedRepetition.ReviewItem due = dueItems.get(i);
            dueNow.add(Map.of(
                    "knowledge_id", due.getKnowledgeId(),
                    "overdue_days", due.getOverdueDays()
            ));
        }

        Map<String, Object> data = new HashMap<>();
        data.put("due_now", dueNow);
        data.put("weekly_schedule", weeklySchedule);
        publisher.publishEvent(new AgentEvent(this, EventType.REVIEW_SCHEDULED,
                "CurriculumAgent", learnerId, data, correlationId));
    }

    private void checkAndRecommendNext(String learnerId, String correlationId) {
        Set<String> masteredIds = getMasteredIds(learnerId);
        List<String> ready = knowledgeGraph.getReadyNodes(masteredIds);

        if (!ready.isEmpty()) {
            String nextTopic = ready.get(0);
            KnowledgeGraph.KnowledgeNode node = knowledgeGraph.getNode(nextTopic);

            Map<String, Object> data = new HashMap<>();
            data.put("knowledge_id", nextTopic);
            data.put("name", node != null ? node.name() : nextTopic);
            data.put("difficulty", node != null ? node.difficulty() : 0.5);
            data.put("reason", "前置知识已掌握，推荐学习新内容");
            data.put("alternatives", ready.subList(1, Math.min(4, ready.size())));
            publisher.publishEvent(new AgentEvent(this, EventType.NEXT_TOPIC,
                    "CurriculumAgent", learnerId, data, correlationId));
        }
    }

    private Set<String> getMasteredIds(String learnerId) {
        Set<String> mastered = new HashSet<>();
        Map<String, SpacedRepetition.ReviewItem> items = reviewItems.get(learnerId);
        if (items != null) {
            for (var entry : items.entrySet()) {
                if (entry.getValue().getEasinessFactor() >= 2.0) {
                    mastered.add(entry.getKey());
                }
            }
        }
        return mastered;
    }

    private SpacedRepetition.ReviewItem getReviewItem(String learnerId, String knowledgeId) {
        return reviewItems
                .computeIfAbsent(learnerId, k -> new ConcurrentHashMap<>())
                .computeIfAbsent(knowledgeId, SpacedRepetition.ReviewItem::new);
    }

    private int masteryToQuality(double mastery) {
        if (mastery >= 0.9) return 5;
        if (mastery >= 0.75) return 4;
        if (mastery >= 0.6) return 3;
        if (mastery >= 0.4) return 2;
        if (mastery >= 0.2) return 1;
        return 0;
    }
}
