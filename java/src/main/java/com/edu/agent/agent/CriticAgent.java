package com.edu.agent.agent;

import com.edu.agent.core.AgentEvent;
import com.edu.agent.core.EventType;
import com.edu.agent.db.entity.Critique;
import com.edu.agent.db.repository.CritiqueRepository;
import com.edu.agent.service.CriticService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Critic Agent -- LLM-as-judge 教学回复评估 + 自反思再生成(P2#16a)。
 *
 * <p>对齐 Python critic_agent.py:
 * <ol>
 *   <li>订阅 TEACHING_RESPONSE 事件</li>
 *   <li>用 CriticService 评估回复质量(4 维度 + overall 1-5 分)</li>
 *   <li>低分(overall <= 3)时触发自反思: 把 critique 作为反馈让 Tutor 重新生成</li>
 *   <li>发布 TEACHING_CRITICIZED 事件携带评估结果</li>
 * </ol>
 *
 * <p>设计原则:
 * <ul>
 *   <li>失败降级: LLM 不可用时跳过评估不阻塞主流程</li>
 *   <li>单次重生成: 最多重生成一次,避免循环(regenerated=True 的事件不再评估)</li>
 *   <li>不修改 TutorAgent: 通过事件订阅解耦</li>
 * </ul>
 */
@Component
public class CriticAgent {

    private static final Logger log = LoggerFactory.getLogger(CriticAgent.class);

    private final ApplicationEventPublisher publisher;
    private final CriticService criticService;
    private final CritiqueRepository critiqueRepository;
    /** 防循环: 已触发重生成的 teaching event ID 集合。 */
    private final Set<String> regenerating = ConcurrentHashMap.newKeySet();

    public CriticAgent(ApplicationEventPublisher publisher,
                       CriticService criticService,
                       CritiqueRepository critiqueRepository) {
        this.publisher = publisher;
        this.criticService = criticService;
        this.critiqueRepository = critiqueRepository;
    }

    @EventListener(condition = "#event.type == T(com.edu.agent.core.EventType).TEACHING_RESPONSE")
    public void handleTeachingResponse(AgentEvent event) {
        // 跳过自己发布的重生成事件,避免循环
        if (Boolean.TRUE.equals(event.getData().get("regenerated"))) {
            return;
        }
        // 跳过 hint 转发(无 LLM 评估意义)
        if ("hint".equals(event.getData().get("teaching_style"))) {
            return;
        }

        String learnerId = event.getLearnerId();
        String knowledgeId = (String) event.getData().getOrDefault("knowledge_id", "");
        String responseText = (String) event.getData().getOrDefault("response", "");
        String level = (String) event.getData().getOrDefault("difficulty_level", "beginner");
        double mastery = ((Number) event.getData().getOrDefault("mastery", 0.0)).doubleValue();
        Boolean isCorrect = (Boolean) event.getData().get("is_correct");
        String question = (String) event.getData().getOrDefault("question", "");

        // 1. 评估
        CriticService.CritiqueResult critique = criticService.evaluate(
                knowledgeId, level, mastery, isCorrect, responseText, question);

        if (critique == null) {
            log.debug("[Critic] skipped (LLM unavailable) event={}", event.getId());
            return;
        }

        // 2. 持久化评估结果
        Critique entity = new Critique();
        entity.setLearnerId(learnerId);
        entity.setKnowledgeId(knowledgeId);
        entity.setTeachingEventId(event.getId());
        entity.setOverall((short) critique.overall());
        entity.setScores(critique.scores());
        entity.setCritique(critique.critique());
        entity.setNeedsRegeneration(critique.needsRegeneration());
        entity.setOriginalResponse(responseText);
        entity.setCriticModel(critique.model());
        entity.setCriticTokens(critique.tokens());
        critiqueRepository.save(entity);

        // 3. 发布 TEACHING_CRITICIZED
        Map<String, Object> critiqueData = new HashMap<>();
        critiqueData.put("knowledge_id", knowledgeId);
        critiqueData.put("teaching_event_id", event.getId());
        critiqueData.put("overall", critique.overall());
        critiqueData.put("scores", critique.scores());
        critiqueData.put("critique", critique.critique());
        critiqueData.put("needs_regeneration", critique.needsRegeneration());
        critiqueData.put("critic_model", critique.model());
        critiqueData.put("critic_tokens", critique.tokens());
        publisher.publishEvent(new AgentEvent(this, EventType.TEACHING_CRITICIZED,
                "CriticAgent", learnerId, critiqueData, event.getCorrelationId()));

        // 4. 低分 -> 触发自反思再生成
        if (critique.needsRegeneration() && regenerating.add(event.getId())) {
            regenerateAndPublish(event, knowledgeId, level, mastery, isCorrect,
                    question, responseText, critique);
        }
    }

    private void regenerateAndPublish(AgentEvent event, String knowledgeId, String level,
                                      double mastery, Boolean isCorrect, String question,
                                      String originalResponse, CriticService.CritiqueResult critique) {
        try {
            CriticService.RegenerationResult regen = criticService.regenerate(
                    knowledgeId, level, mastery, isCorrect, originalResponse,
                    critique.critique(), question);

            Map<String, Object> payload = new HashMap<>();
            payload.put("knowledge_id", knowledgeId);
            payload.put("response", regen.text());
            payload.put("teaching_style", event.getData().getOrDefault("teaching_style", "socratic"));
            payload.put("difficulty_level", level);
            payload.put("regenerated", true);
            payload.put("critic_overall", critique.overall());
            payload.put("critic_critique", critique.critique());
            payload.putAll(regen.metadata());
            publisher.publishEvent(new AgentEvent(this, EventType.TEACHING_RESPONSE,
                    "CriticAgent", event.getLearnerId(), payload, event.getCorrelationId()));

            log.info("[Critic] regenerated response (overall={}, learner={})",
                    critique.overall(), event.getLearnerId());
        } finally {
            regenerating.remove(event.getId());
        }
    }
}
