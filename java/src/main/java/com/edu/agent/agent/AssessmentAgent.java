package com.edu.agent.agent;

import com.edu.agent.core.AgentEvent;
import com.edu.agent.core.EventType;
import com.edu.agent.core.LearnerModel;
import com.edu.agent.service.LearnerModelService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import java.util.HashMap;
import java.util.Map;

/**
 * Assessment Agent -- BKT 知识追踪评估。
 * <p>
 * 使用 Spring @EventListener 同步分发；掌握度经 {@link LearnerModelService} L1/L2。
 */
@Component
public class AssessmentAgent {

    private static final Logger log = LoggerFactory.getLogger(AssessmentAgent.class);
    private final ApplicationEventPublisher publisher;
    private final LearnerModelService learnerModelService;

    public AssessmentAgent(ApplicationEventPublisher publisher, LearnerModelService learnerModelService) {
        this.publisher = publisher;
        this.learnerModelService = learnerModelService;
    }

    public Map<String, LearnerModel> getLearnerModels() {
        return learnerModelService.getCache();
    }

    @EventListener(condition = "#event.type == T(com.edu.agent.core.EventType).STUDENT_SUBMISSION")
    public void handleSubmission(AgentEvent event) {
        String learnerId = event.getLearnerId();
        String knowledgeId = (String) event.getData().getOrDefault("knowledge_id", "");
        boolean isCorrect = (boolean) event.getData().getOrDefault("is_correct", false);

        LearnerModel model = learnerModelService.getOrLoad(learnerId);
        LearnerModel.KnowledgeState state = model.updateMastery(knowledgeId, isCorrect);

        log.info("[Assessment] learner={}, kp={}, correct={}, mastery={} ({})",
                learnerId, knowledgeId, isCorrect, state.getMastery(), state.getLevel());

        Map<String, Object> data = new HashMap<>();
        data.put("knowledge_id", knowledgeId);
        data.put("mastery", state.getMastery());
        data.put("level", state.getLevel());
        data.put("is_correct", isCorrect);
        data.put("attempts", state.getAttempts());
        publisher.publishEvent(new AgentEvent(this, EventType.MASTERY_UPDATED,
                "AssessmentAgent", learnerId, data));

        if (state.getMastery() < 0.3 && state.getAttempts() >= 3) {
            Map<String, Object> weakData = new HashMap<>();
            weakData.put("knowledge_id", knowledgeId);
            weakData.put("mastery", state.getMastery());
            publisher.publishEvent(new AgentEvent(this, EventType.WEAKNESS_DETECTED,
                    "AssessmentAgent", learnerId, weakData));
        }

        Map<String, Object> completeData = new HashMap<>(data);
        completeData.put("overall_progress", model.getOverallProgress());
        publisher.publishEvent(new AgentEvent(this, EventType.ASSESSMENT_COMPLETE,
                "AssessmentAgent", learnerId, completeData));
    }
}
