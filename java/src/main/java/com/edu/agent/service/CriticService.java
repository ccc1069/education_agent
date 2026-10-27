package com.edu.agent.service;

import com.edu.agent.llm.LlmRequest;
import com.edu.agent.llm.LlmResponse;
import com.edu.agent.llm.LlmService;
import com.edu.agent.llm.LlmUnavailableException;
import com.edu.agent.llm.Prompts;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * LLM-as-judge Critic 服务 -- 对齐 Python llm/critic_service.py。
 *
 * <p>评估教学回复 + 自反思再生成:
 * <ul>
 *   <li>evaluate(): 对 TutorAgent 的回复打分(4 维度 + overall + critique)</li>
 *   <li>regenerate(): 把 critique 作为反馈,重新生成回复</li>
 * </ul>
 *
 * <p>当前为 stub 实现(无 LLM 时降级)。当配置 app.llm.api-key 时,可接入真实 LLM。
 * LLM 不可用时返回 heuristic 评分(基于文本特征),不阻塞主流程。
 */
@Slf4j
@Service
public class CriticService {

    private static final List<String> DIMENSIONS = List.of(
            "pedagogical", "appropriateness", "clarity", "engagement");
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final LlmService llmService;

    public CriticService(LlmService llmService) {
        this.llmService = llmService;
    }

    /**
     * 评估教学回复。LLM 不可用时降级到启发式评分。
     */
    public CritiqueResult evaluate(String knowledgeId, String level, double mastery,
                                   Boolean isCorrect, String teachingResponse,
                                   String learnerMessage) {
        String userPrompt = Prompts.buildCriticUserPrompt(
                learnerMessage != null ? learnerMessage : "学生提问",
                teachingResponse,
                level);

        try {
            LlmResponse llmResponse = llmService.chat(
                    new LlmRequest(Prompts.CRITIC_SYSTEM_PROMPT, userPrompt));
            return parseCriticJson(llmResponse.content(), llmResponse.model(), llmResponse.totalTokens());
        } catch (LlmUnavailableException e) {
            log.info("[CriticService] LLM 不可用,降级到启发式评分: {}", e.getMessage());
        } catch (Exception e) {
            log.warn("[CriticService] LLM 响应解析失败,降级到启发式: {}", e.getMessage());
        }

        // 降级:启发式评分
        return heuristicEvaluate(teachingResponse);
    }

    /**
     * 根据 critique 重新生成教学回复。失败时降级到原回复。
     */
    public RegenerationResult regenerate(String knowledgeId, String level, double mastery,
                                         Boolean isCorrect, String originalResponse,
                                         String critique, String learnerMessage) {
        String systemPrompt = Prompts.getTutorPrompt(level);
        String userPrompt = Prompts.sanitize(String.format(
                "原回复:\n%s\n\n评审意见:\n%s\n\n请根据评审意见重新生成一段教学回复,保持苏格拉底式引导风格。",
                originalResponse, critique));

        try {
            String newResponse = llmService.chatOrFallback(new LlmRequest(systemPrompt, userPrompt));
            if (newResponse != null && !newResponse.isBlank()) {
                return new RegenerationResult(newResponse, Map.of(
                        "llm_used", true,
                        "fallback", "none",
                        "regenerated", true));
            }
        } catch (LlmUnavailableException e) {
            log.info("[CriticService] LLM 不可用,regenerate 降级到原回复: {}", e.getMessage());
        }

        // 降级:返回原回复
        return new RegenerationResult(originalResponse, Map.of(
                "llm_used", false,
                "fallback", "original",
                "regenerated", false));
    }

    /**
     * 解析 Critic LLM 返回的 JSON。
     */
    private CritiqueResult parseCriticJson(String content, String model, int tokens) {
        try {
            // 提取 JSON(可能包含 ```json 包裹)
            String jsonStr = content;
            if (jsonStr.contains("```json")) {
                int start = jsonStr.indexOf("```json") + 7;
                int end = jsonStr.indexOf("```", start);
                jsonStr = jsonStr.substring(start, end);
            } else if (jsonStr.contains("```")) {
                int start = jsonStr.indexOf("```") + 3;
                int end = jsonStr.indexOf("```", start);
                jsonStr = jsonStr.substring(start, end);
            }
            jsonStr = jsonStr.trim();

            JsonNode root = MAPPER.readTree(jsonStr);
            JsonNode scoresNode = root.path("scores");

            Map<String, Object> scores = new HashMap<>();
            for (String dim : DIMENSIONS) {
                scores.put(dim, scoresNode.path(dim).asDouble(3.0));
            }

            double overall = root.path("overall").asDouble(
                    scores.values().stream().mapToDouble(v -> ((Number) v).doubleValue()).average().orElse(3.0));
            String critiqueText = root.path("critique").asText("无具体建议");
            boolean needsRegeneration = root.path("needs_regeneration").asBoolean(overall < 3.0);

            return new CritiqueResult(scores, (int) Math.round(overall), critiqueText,
                    needsRegeneration, model, tokens);
        } catch (Exception e) {
            log.warn("[CriticService] JSON 解析失败,降级到启发式: {}", e.getMessage());
            return heuristicEvaluate(content);
        }
    }

    /**
     * 启发式评分(无 LLM 时的降级策略)。
     * 基于回复长度、是否包含提问、是否包含鼓励语等特征。
     */
    private CritiqueResult heuristicEvaluate(String response) {
        if (response == null || response.isBlank()) {
            return new CritiqueResult(Map.of(
                    "pedagogical", 2, "appropriateness", 2, "clarity", 2, "engagement", 2),
                    2, "回复为空", true, "heuristic", 0);
        }

        int len = response.length();
        boolean hasQuestion = response.contains("?") || response.contains("？");
        boolean hasEncouragement = response.contains("好") || response.contains("很好")
                || response.contains("不错") || response.contains("加油");
        boolean hasGuidance = response.contains("试着") || response.contains("想一想")
                || response.contains("思考") || response.contains("引导");

        int pedagogical = clamp(1, 5, 3 + (hasGuidance ? 1 : 0) + (hasQuestion ? 1 : 0));
        int appropriateness = clamp(1, 5, 3 + (hasEncouragement ? 1 : 0));
        int clarity = clamp(1, 5, len > 50 ? 4 : 3);
        int engagement = clamp(1, 5, 3 + (hasQuestion ? 1 : 0) + (hasEncouragement ? 1 : 0));
        int overall = (pedagogical + appropriateness + clarity + engagement) / 4;

        Map<String, Object> scores = new HashMap<>();
        scores.put("pedagogical", pedagogical);
        scores.put("appropriateness", appropriateness);
        scores.put("clarity", clarity);
        scores.put("engagement", engagement);

        String critiqueText = overall <= 3
                ? "回复可改进: 建议增加引导性提问和鼓励语"
                : "回复质量良好,包含有效教学策略";

        return new CritiqueResult(scores, overall, critiqueText, overall <= 3, "heuristic", 0);
    }

    private static int clamp(int min, int max, int val) {
        return Math.max(min, Math.min(max, val));
    }

    /** 评估结果。 */
    public record CritiqueResult(
            Map<String, Object> scores,
            int overall,
            String critique,
            boolean needsRegeneration,
            String model,
            int tokens
    ) {}

    /** 再生成结果。 */
    public record RegenerationResult(String text, Map<String, Object> metadata) {}
}
