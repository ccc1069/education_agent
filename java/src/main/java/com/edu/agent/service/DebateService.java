package com.edu.agent.service;

import com.edu.agent.llm.LlmRequest;
import com.edu.agent.llm.LlmResponse;
import com.edu.agent.llm.LlmService;
import com.edu.agent.llm.LlmUnavailableException;
import com.edu.agent.llm.Prompts;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.Map;

/**
 * Multi-Agent Debate 服务 -- 对齐 Python llm/debate_service.py。
 *
 * <p>2-persona 辩论(socratic vs direct),N 轮互相批评+修订,Synthesizer 综合产出 consensus。
 *
 * <p>当前为 stub 实现(无 LLM 时降级为启发式综合)。当配置 app.llm.api-key 时可接入真实 LLM。
 */
@Slf4j
@Service
public class DebateService {

    /** 默认辩论轮次(对齐 Python DEFAULT_ROUNDS=2)。 */
    private static final int DEFAULT_ROUNDS = 2;
    private static final int MAX_ROUNDS = 4;
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final LlmService llmService;
    private final int rounds;

    public DebateService(LlmService llmService,
                         @Value("${app.llm.debate-rounds:2}") int rounds) {
        this.llmService = llmService;
        this.rounds = Math.max(1, Math.min(rounds, MAX_ROUNDS));
    }

    /**
     * 运行完整辩论流程。LLM 不可用时降级到启发式综合。
     *
     * <p>对齐 Python DebateLLMService.run_debate(LangGraph 简化为 N 轮顺序循环)。
     */
    public DebateResult runDebate(String knowledgeId, String level, double mastery, String question) {
        String topic = Prompts.sanitize(knowledgeId + ": " + question);

        try {
            // 第 1 轮:Socratic vs Direct 各陈词
            String socraticArg = llmDebateTurn(Prompts.DEBATE_SOCRATIC_PROMPT, topic, null);
            String directArg = llmDebateTurn(Prompts.DEBATE_DIRECT_PROMPT, topic, null);

            // 中间轮:互相批评+修订(简化:基于对方观点再论述)
            for (int r = 1; r < rounds; r++) {
                socraticArg = llmDebateTurn(Prompts.DEBATE_SOCRATIC_PROMPT, topic,
                        "对方观点: " + directArg + "\n请基于对方观点进一步阐述。");
                directArg = llmDebateTurn(Prompts.DEBATE_DIRECT_PROMPT, topic,
                        "对方观点: " + socraticArg + "\n请基于对方观点进一步阐述。");
            }

            // Synthesizer 综合
            String synthesisUserPrompt = Prompts.buildDebateContextPrompt(topic, socraticArg, directArg);
            LlmResponse synthesisResp = llmService.chat(
                    new LlmRequest(Prompts.SYNTHESIZER_PROMPT, synthesisUserPrompt));

            String consensus = parseSynthesis(synthesisResp.content(), socraticArg, directArg);

            Map<String, Object> meta = new HashMap<>();
            meta.put("llm_used", true);
            meta.put("rounds", rounds);
            meta.put("personas", "socratic,direct");
            meta.put("orchestrator", "sequential_loop");
            meta.put("model", synthesisResp.model());

            return new DebateResult(consensus, socraticArg, directArg, rounds, meta);

        } catch (LlmUnavailableException e) {
            log.info("[DebateService] LLM 不可用,降级到启发式辩论: {}", e.getMessage());
        } catch (Exception e) {
            log.warn("[DebateService] LLM 辩论过程异常,降级到启发式: {}", e.getMessage());
        }

        // 降级:启发式综合
        return heuristicDebate(knowledgeId, level, mastery, question);
    }

    /**
     * 单轮辩论 LLM 调用,返回 argument 文本。
     */
    private String llmDebateTurn(String systemPrompt, String topic, String context) {
        String userPrompt = context != null
                ? topic + "\n\n" + context + "\n\n```json"
                : topic + "\n\n请陈述你的立场。\n```json";
        try {
            LlmResponse resp = llmService.chat(new LlmRequest(systemPrompt, Prompts.sanitize(userPrompt)));
            return extractArgument(resp.content());
        } catch (LlmUnavailableException e) {
            throw e;
        } catch (Exception e) {
            log.warn("[DebateService] 单轮辩论 LLM 调用失败: {}", e.getMessage());
            throw new RuntimeException("辩论轮次失败", e);
        }
    }

    /**
     * 从 JSON 响应中提取 argument 字段。
     */
    private String extractArgument(String content) {
        try {
            String jsonStr = content;
            if (jsonStr.contains("```json")) {
                jsonStr = jsonStr.substring(jsonStr.indexOf("```json") + 7);
            }
            if (jsonStr.contains("```")) {
                jsonStr = jsonStr.substring(0, jsonStr.indexOf("```"));
            }
            JsonNode root = MAPPER.readTree(jsonStr.trim());
            return root.path("argument").asText(content);
        } catch (Exception e) {
            return content;
        }
    }

    /**
     * 解析 Synthesizer JSON,提取 synthesis 字段。
     */
    private String parseSynthesis(String content, String socraticArg, String directArg) {
        try {
            String jsonStr = content;
            if (jsonStr.contains("```json")) {
                jsonStr = jsonStr.substring(jsonStr.indexOf("```json") + 7);
            }
            if (jsonStr.contains("```")) {
                jsonStr = jsonStr.substring(0, jsonStr.indexOf("```"));
            }
            JsonNode root = MAPPER.readTree(jsonStr.trim());
            String synthesis = root.path("synthesis").asText(null);
            if (synthesis != null && !synthesis.isBlank()) {
                return synthesis;
            }
            // fallback:consensus + synthesis
            return root.path("consensus").asText("") + "\n\n" + root.path("synthesis").asText("");
        } catch (Exception e) {
            // 综合失败时拼接双方观点
            return "【综合】\n苏格拉底式: " + socraticArg.substring(0, Math.min(150, socraticArg.length()))
                    + "\n\n直接论辩式: " + directArg.substring(0, Math.min(150, directArg.length()));
        }
    }

    /**
     * 启发式辩论综合(无 LLM 时的降级策略)。
     * 生成 socratic 和 direct 两种风格的回复,综合为 consensus。
     */
    private DebateResult heuristicDebate(String knowledgeId, String level, double mastery, String question) {
        String socratic = String.format(
                "关于「%s」,让我们一起来思考:%s\n\n" +
                "首先,你认为这个问题的关键点是什么?试着说说你的理解。\n" +
                "如果卡住了,可以想想:这个知识点和之前学过的哪些内容有关?",
                knowledgeId, question);

        String direct = String.format(
                "关于「%s」的直接讲解:%s\n\n" +
                "核心概念:这是%s级别的重要知识点。当前掌握度:%.0f%%。\n" +
                "建议:通过例题巩固理解,然后尝试变式练习。",
                knowledgeId, question, level, mastery * 100);

        String consensus = String.format(
                "【综合回复】关于「%s」:\n\n" +
                "启发式引导:%s\n\n" +
                "直接讲解:%s\n\n" +
                "建议:先理解概念,再通过练习巩固。",
                knowledgeId,
                socratic.substring(0, Math.min(80, socratic.length())),
                direct.substring(0, Math.min(80, direct.length())));

        Map<String, Object> meta = new HashMap<>();
        meta.put("llm_used", false);
        meta.put("rounds", rounds);
        meta.put("personas", "socratic,direct");
        meta.put("orchestrator", "heuristic_stub");

        return new DebateResult(consensus, socratic, direct, rounds, meta);
    }

    /** 辩论结果。 */
    public record DebateResult(
            String consensus,
            String socraticFinal,
            String directFinal,
            int roundsCompleted,
            Map<String, Object> metadata
    ) {}
}
