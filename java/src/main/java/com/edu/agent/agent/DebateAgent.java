package com.edu.agent.agent;

import com.edu.agent.core.AgentEvent;
import com.edu.agent.core.EventType;
import com.edu.agent.service.DebateService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import java.util.HashMap;
import java.util.Map;

/**
 * Debate Agent -- Multi-Agent Debate 多 persona 辩论综合(P2#16b)。
 *
 * <p>对齐 Python debate_agent.py:
 * <ol>
 *   <li>订阅 STUDENT_QUESTION 事件(仅在 data.debate_mode=true 时触发)</li>
 *   <li>启动 2-persona 辩论(socratic vs direct),N 轮互相批评+修订</li>
 *   <li>Synthesizer 综合两版最终回复,产出 consensus</li>
 *   <li>发布 DEBATE_CONSENSUS 事件携带最终回复</li>
 * </ol>
 *
 * <p>设计原则:
 * <ul>
 *   <li>显式触发: 默认不启用,需 debate_mode=true(避免 LLM 成本)</li>
 *   <li>旁路解耦: 不修改 TutorAgent,DebateAgent 是可选增强路径</li>
 *   <li>失败降级: LLM 不可用时静默跳过</li>
 * </ul>
 */
@Component
public class DebateAgent {

    private static final Logger log = LoggerFactory.getLogger(DebateAgent.class);

    private final ApplicationEventPublisher publisher;
    private final DebateService debateService;

    public DebateAgent(ApplicationEventPublisher publisher, DebateService debateService) {
        this.publisher = publisher;
        this.debateService = debateService;
    }

    @EventListener(condition = "#event.type == T(com.edu.agent.core.EventType).STUDENT_QUESTION")
    public void handleStudentQuestion(AgentEvent event) {
        // 仅在显式 debate_mode=true 时触发
        if (!Boolean.TRUE.equals(event.getData().get("debate_mode"))) {
            return;
        }

        String learnerId = event.getLearnerId();
        String knowledgeId = (String) event.getData().getOrDefault("knowledge_id", "general");
        String question = (String) event.getData().getOrDefault("question", "");
        String level = (String) event.getData().getOrDefault("level", "beginner");
        double mastery = ((Number) event.getData().getOrDefault("mastery", 0.0)).doubleValue();

        if (question == null || question.isBlank()) {
            log.debug("[Debate] skipped: no question");
            return;
        }

        DebateService.DebateResult result = debateService.runDebate(
                knowledgeId, level, mastery, question);

        if (result == null || result.consensus() == null || result.consensus().isBlank()) {
            log.debug("[Debate] produced no consensus");
            return;
        }

        Map<String, Object> payload = new HashMap<>();
        payload.put("knowledge_id", knowledgeId);
        payload.put("question", question);
        payload.put("response", result.consensus());
        payload.put("teaching_style", "debate_synthesis");
        payload.put("difficulty_level", level);
        payload.put("socratic_final", result.socraticFinal());
        payload.put("direct_final", result.directFinal());
        payload.put("rounds_completed", result.roundsCompleted());
        payload.put("regenerated", false);
        payload.putAll(result.metadata());

        publisher.publishEvent(new AgentEvent(this, EventType.DEBATE_CONSENSUS,
                "DebateAgent", learnerId, payload, event.getCorrelationId()));

        log.info("[Debate] consensus published (rounds={}, learner={})",
                result.roundsCompleted(), learnerId);
    }
}
