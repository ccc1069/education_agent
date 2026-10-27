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
 * Tutor Agent -- 苏格拉底式教学。
 *
 * 4级Prompt策略：beginner / developing / proficient / mastered
 * 不直接给答案，通过反问引导思考。
 */
@Component
public class TutorAgent {

    private static final Logger log = LoggerFactory.getLogger(TutorAgent.class);
    private final ApplicationEventPublisher publisher;
    private final LlmService llmService;
    private final Map<String, Integer> studentAttempts = new ConcurrentHashMap<>();

    private static final Map<String, String> SOCRATIC_PROMPTS = Map.of(
        "beginner",
            "你是一位耐心的数学老师，学生刚开始学习这个知识点。\n" +
            "请用最简单的语言和例子帮助学生理解概念。\n" +
            "不要直接给答案，而是：\n" +
            "1. 先问学生对相关基础概念是否了解\n" +
            "2. 用生活化的类比帮助理解\n" +
            "3. 给一个最简单的例题让学生尝试",
        "developing",
            "你是一位苏格拉底式的数学老师，学生正在学习中。\n" +
            "请通过提问引导学生思考：\n" +
            "1. 问学生已经知道哪些相关知识\n" +
            "2. 引导学生发现问题的关键步骤\n" +
            "3. 当学生卡住时，给一个关键提示而非答案",
        "proficient",
            "你是一位挑战型的数学老师，学生已经比较熟练。\n" +
            "请：\n" +
            "1. 提出更深层的思考问题（为什么？还有其他方法吗？）\n" +
            "2. 引导学生发现知识点之间的联系\n" +
            "3. 给出变式题目拓展思维",
        "mastered",
            "你是一位高级数学导师，学生已掌握此知识点。\n" +
            "请：\n" +
            "1. 引导学生总结归纳方法论\n" +
            "2. 布置综合性、跨知识点的挑战题\n" +
            "3. 鼓励学生尝试教别人（费曼学习法）"
    );

    public TutorAgent(ApplicationEventPublisher publisher, LlmService llmService) {
        this.publisher = publisher;
        this.llmService = llmService;
    }

    @EventListener(condition = "#event.type == T(com.edu.agent.core.EventType).ASSESSMENT_COMPLETE")
    public void handleAssessment(AgentEvent event) {
        String learnerId = event.getLearnerId();
        String knowledgeId = (String) event.getData().getOrDefault("knowledge_id", "");
        String level = (String) event.getData().getOrDefault("level", "beginner");
        Boolean isCorrect = (Boolean) event.getData().get("is_correct");
        double mastery = ((Number) event.getData().getOrDefault("mastery", 0.0)).doubleValue();

        if (Boolean.FALSE.equals(isCorrect)) {
            String key = learnerId + ":" + knowledgeId;
            int attempts = studentAttempts.merge(key, 1, Integer::sum);
            if (attempts >= 2) {
                Map<String, Object> hintData = new HashMap<>();
                hintData.put("knowledge_id", knowledgeId);
                hintData.put("mastery", mastery);
                hintData.put("attempts", attempts);
                hintData.put("level", level);
                publisher.publishEvent(new AgentEvent(this, EventType.HINT_NEEDED,
                        "TutorAgent", learnerId, hintData, event.getCorrelationId()));
                return;
            }
        }

        String response = generateSocraticResponse(knowledgeId, level, mastery, isCorrect);

        Map<String, Object> data = new HashMap<>();
        data.put("knowledge_id", knowledgeId);
        data.put("response", response);
        data.put("teaching_style", "socratic");
        data.put("difficulty_level", level);
        data.put("prompt_template_used", level);
        publisher.publishEvent(new AgentEvent(this, EventType.TEACHING_RESPONSE,
                "TutorAgent", learnerId, data, event.getCorrelationId()));
    }

    @EventListener(condition = "#event.type == T(com.edu.agent.core.EventType).STUDENT_MESSAGE")
    public void handleStudentMessage(AgentEvent event) {
        String knowledgeId = (String) event.getData().getOrDefault("knowledge_id", "general");
        String message = (String) event.getData().getOrDefault("question", "");
        String response = String.format(
                "好的，关于「%s」，你的问题是：%s\n在我回答之前，让我先问你：\n你对这个知识点已经了解了哪些内容？试着说说你的理解。",
                knowledgeId, message);

        Map<String, Object> data = new HashMap<>();
        data.put("knowledge_id", knowledgeId);
        data.put("response", response);
        data.put("teaching_style", "socratic");
        data.put("difficulty_level", "adaptive");
        publisher.publishEvent(new AgentEvent(this, EventType.TEACHING_RESPONSE,
                "TutorAgent", event.getLearnerId(), data, event.getCorrelationId()));
    }

    @EventListener(condition = "#event.type == T(com.edu.agent.core.EventType).HINT_RESPONSE")
    public void handleHintResponse(AgentEvent event) {
        Map<String, Object> data = new HashMap<>();
        data.put("knowledge_id", event.getData().getOrDefault("knowledge_id", ""));
        data.put("response", event.getData().getOrDefault("hint_text", ""));
        data.put("teaching_style", "hint");
        data.put("hint_level", event.getData().getOrDefault("hint_level", 1));
        publisher.publishEvent(new AgentEvent(this, EventType.TEACHING_RESPONSE,
                "TutorAgent", event.getLearnerId(), data, event.getCorrelationId()));
    }

    @EventListener(condition = "#event.type == T(com.edu.agent.core.EventType).ENGAGEMENT_ALERT")
    public void handleEngagementAlert(AgentEvent event) {
        String alertType = (String) event.getData().getOrDefault("alert_type", "");
        Map<String, Object> data = new HashMap<>();
        if ("frustration".equals(alertType)) {
            data.put("action", "decrease");
            data.put("reason", "检测到学生挫败感");
            data.put("message", "我注意到你可能遇到了困难，让我们换一个角度来看这个问题，从更简单的地方开始。");
        } else if ("boredom".equals(alertType)) {
            data.put("action", "increase");
            data.put("reason", "检测到学生可能感到无聊");
            data.put("message", "看起来这对你来说太简单了！让我给你一个更有挑战性的问题。");
        }
        if (!data.isEmpty()) {
            publisher.publishEvent(new AgentEvent(this, EventType.DIFFICULTY_ADJUSTED,
                    "TutorAgent", event.getLearnerId(), data, event.getCorrelationId()));
        }
    }

    /**
     * 生成苏格拉底式回复 -- 优先 LLM,不可用时降级到启发式模板。
     */
    private String generateSocraticResponse(String knowledgeId, String level, double mastery, Boolean isCorrect) {
        String systemPrompt = Prompts.getTutorPrompt(level);
        String userPrompt = buildUserPrompt(knowledgeId, level, mastery, isCorrect);

        try {
            String llmResponse = llmService.chatOrFallback(new LlmRequest(systemPrompt, userPrompt));
            if (llmResponse != null && !llmResponse.isBlank()) {
                log.debug("[TutorAgent] LLM 生成回复: knowledgeId={}", knowledgeId);
                return llmResponse;
            }
        } catch (LlmUnavailableException e) {
            log.debug("[TutorAgent] LLM 不可用,降级到启发式模板: {}", e.getMessage());
        }

        // 降级:启发式模板
        return heuristicResponse(knowledgeId, level, mastery, isCorrect);
    }

    private String buildUserPrompt(String knowledgeId, String level, double mastery, Boolean isCorrect) {
        if (Boolean.TRUE.equals(isCorrect)) {
            return Prompts.sanitize(String.format(
                    "学生在知识点「%s」的练习中答对了。当前掌握度 %.0f%%,水平 %s。\n" +
                    "请生成一段苏格拉底式追问,引导学生深化理解。", knowledgeId, mastery * 100, level));
        } else if (Boolean.FALSE.equals(isCorrect)) {
            return Prompts.sanitize(String.format(
                    "学生在知识点「%s」的练习中答错了。当前掌握度 %.0f%%,水平 %s。\n" +
                    "请生成一段苏格拉底式引导,不要给答案,用提问帮助学生找到错误原因。", knowledgeId, mastery * 100, level));
        }
        return Prompts.sanitize(String.format("学生开始学习知识点「%s」,水平 %s。请用苏格拉底式提问引导学生入门。", knowledgeId, level));
    }

    private String heuristicResponse(String knowledgeId, String level, double mastery, Boolean isCorrect) {
        String prompt = SOCRATIC_PROMPTS.getOrDefault(level, SOCRATIC_PROMPTS.get("beginner"));

        if (Boolean.TRUE.equals(isCorrect)) {
            return String.format(
                    "很好！你在「%s」上的表现不错。当前掌握度：%.0f%%。\n" +
                    "让我问你一个更深入的问题：你能用自己的话解释一下这个概念吗？\n" +
                    "或者，你觉得这个知识点和之前学过的哪个知识点有联系？\n\n" +
                    "[教学策略: %s]", knowledgeId, mastery * 100, prompt.substring(0, Math.min(30, prompt.length())) + "...]");
        } else if (Boolean.FALSE.equals(isCorrect)) {
            return String.format(
                    "没关系，让我们一起来分析「%s」。\n" +
                    "先不看答案，我想问你几个问题：\n" +
                    "1. 你觉得这道题考查的是什么知识点？\n" +
                    "2. 你做题的时候卡在了哪一步？\n" +
                    "3. 能不能先试试用最简单的数字代入看看？\n\n" +
                    "[教学策略: %s]", knowledgeId, prompt.substring(0, Math.min(30, prompt.length())) + "...]");
        }
        return String.format("关于「%s」，你已经了解了哪些内容？试着说说你的理解。", knowledgeId);
    }
}
