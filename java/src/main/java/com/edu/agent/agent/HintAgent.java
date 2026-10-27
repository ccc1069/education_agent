package com.edu.agent.agent;

import com.edu.agent.core.AgentEvent;
import com.edu.agent.core.EventType;
import com.edu.agent.llm.LlmRequest;
import com.edu.agent.llm.LlmService;
import com.edu.agent.llm.LlmUnavailableException;
import com.edu.agent.llm.Prompts;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Hint Agent -- 三级提示策略。
 * Level 1: 元认知暗示  Level 2: 脚手架引导  Level 3: 直接答案
 */
@Component
public class HintAgent {

    private static final Logger log = LoggerFactory.getLogger(HintAgent.class);
    private final ApplicationEventPublisher publisher;
    private final LlmService llmService;
    private final Map<String, Integer> hintHistory = new ConcurrentHashMap<>();

    public HintAgent(ApplicationEventPublisher publisher, LlmService llmService) {
        this.publisher = publisher;
        this.llmService = llmService;
    }

    @EventListener(condition = "#event.type == T(com.edu.agent.core.EventType).HINT_NEEDED")
    public void handleHintNeeded(AgentEvent event) {
        String learnerId = event.getLearnerId();
        String knowledgeId = (String) event.getData().getOrDefault("knowledge_id", "");
        double mastery = ((Number) event.getData().getOrDefault("mastery", 0.0)).doubleValue();
        int attempts = ((Number) event.getData().getOrDefault("attempts", 1)).intValue();

        int level = determineLevel(learnerId, knowledgeId, mastery, attempts);
        String key = learnerId + ":" + knowledgeId;
        hintHistory.merge(key, 1, Integer::sum);

        String hintText = generateHint(knowledgeId, level);
        String levelName = switch (level) {
            case 1 -> "metacognitive";
            case 2 -> "scaffolding";
            case 3 -> "targeted";
            default -> "unknown";
        };

        log.info("[Hint] learner={}, kp={}, level={}", learnerId, knowledgeId, levelName);

        Map<String, Object> data = new HashMap<>();
        data.put("knowledge_id", knowledgeId);
        data.put("hint_level", level);
        data.put("hint_level_name", levelName);
        data.put("hint_text", hintText);
        publisher.publishEvent(new AgentEvent(this, EventType.HINT_RESPONSE,
                "HintAgent", learnerId, data));
    }

    private int determineLevel(String learnerId, String knowledgeId, double mastery, int attempts) {
        String key = learnerId + ":" + knowledgeId;
        int hintCount = hintHistory.getOrDefault(key, 0);

        if (mastery < 0.15 && attempts >= 3) return 3;
        if (hintCount <= 1) return 1;
        if (hintCount <= 3) return 2;
        return 3;
    }

    /**
     * 生成分层提示 -- 优先 LLM,不可用时降级到启发式模板。
     */
    private String generateHint(String knowledgeId, int level) {
        String systemPrompt = Prompts.getHintPrompt(level);
        String userPrompt = Prompts.sanitize(String.format(
                "学生在知识点「%s」上遇到困难,已尝试多次。请生成第 %d 层提示。\n" +
                "要求:不要直接给答案,用引导性语言帮助学生找到解题方向。", knowledgeId, level));

        try {
            String llmResponse = llmService.chatOrFallback(new LlmRequest(systemPrompt, userPrompt));
            if (llmResponse != null && !llmResponse.isBlank()) {
                log.debug("[HintAgent] LLM 生成提示: knowledgeId={}, level={}", knowledgeId, level);
                return llmResponse;
            }
        } catch (LlmUnavailableException e) {
            log.debug("[HintAgent] LLM 不可用,降级到启发式模板: {}", e.getMessage());
        }

        // 降级:启发式模板
        return heuristicHint(knowledgeId, level);
    }

    private String heuristicHint(String knowledgeId, int level) {
        return switch (level) {
            case 1 -> String.format("💡 关于「%s」：想一想，题目里有哪些关键信息你还没用上？", knowledgeId);
            case 2 -> String.format("📝 关于「%s」：试着回忆相关的公式或定义，然后一步步来。", knowledgeId);
            case 3 -> String.format("📖 关于「%s」：让我帮你梳理解题思路，但请你一定要自己重做一遍。", knowledgeId);
            default -> "继续思考...";
        };
    }
}
