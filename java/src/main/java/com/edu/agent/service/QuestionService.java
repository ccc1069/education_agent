package com.edu.agent.service;

import com.edu.agent.db.entity.Question;
import com.edu.agent.db.repository.QuestionRepository;
import com.edu.agent.llm.LlmRequest;
import com.edu.agent.llm.LlmResponse;
import com.edu.agent.llm.LlmService;
import com.edu.agent.llm.LlmUnavailableException;
import com.edu.agent.llm.Prompts;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigInteger;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 题目服务 -- 对齐 Python services/question_service.py。
 * 当前实现为 stub(无 LLM 实际出题),后续接入 LLM 后扩展。
 */
@Slf4j
@Service
public class QuestionService {

    private final QuestionRepository questionRepository;
    private final LlmService llmService;
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private static final Set<String> VALID_STATUSES = Set.of(
            "draft", "review", "published", "rejected", "archived"
    );
    private static final Set<String> VALID_TRANSITIONS_FROM_DRAFT = Set.of("review", "archived");
    private static final Set<String> VALID_TRANSITIONS_FROM_REVIEW = Set.of("published", "rejected", "draft");
    private static final Set<String> VALID_TRANSITIONS_FROM_PUBLISHED = Set.of("archived");
    private static final Set<String> VALID_TRANSITIONS_FROM_REJECTED = Set.of("draft", "archived");
    private static final Set<String> VALID_TRANSITIONS_FROM_ARCHIVED = Set.of("draft");
    private static final Set<String> DELETABLE_STATUSES = Set.of("draft", "rejected", "archived");

    public QuestionService(QuestionRepository questionRepository, LlmService llmService) {
        this.questionRepository = questionRepository;
        this.llmService = llmService;
    }

    /**
     * 生成题目 -- 优先 LLM 出题(JSON 解析),不可用时降级到 stub。
     */
    @Transactional
    public Map<String, Object> generateQuestion(String knowledgeId, String questionType,
                                                  Integer difficulty, Integer createdBy,
                                                  Boolean useRag) {
        if (difficulty == null || difficulty < 1 || difficulty > 5) {
            throw new IllegalArgumentException("难度必须在 1-5 之间");
        }
        String type = questionType == null ? "multiple_choice" : questionType;
        String difficultyLabel = switch (difficulty) {
            case 1, 2 -> "easy";
            case 3 -> "medium";
            default -> "hard";
        };

        // 优先 LLM 出题
        Map<String, Object> content = tryLlmGenerate(knowledgeId, difficultyLabel);

        Question q = new Question();
        q.setTenantId(BigInteger.ONE);
        q.setKnowledgeId(knowledgeId);
        q.setQuestionType(type);
        q.setDifficulty(difficulty);
        q.setAnswer(content.containsKey("correct_answer") ? (String) content.get("correct_answer") : "示例答案");
        q.setAnalysis(content.containsKey("explanation") ? (String) content.get("explanation") : "示例解析");
        q.setStatus("draft");
        q.setCreatedBy(createdBy);
        q.setContent(content);
        q = questionRepository.save(q);
        log.info("Question generated: id={} knowledge={} llm={}", q.getId(), knowledgeId,
                content.containsKey("_llm_generated"));
        return toDetailMap(q, true);
    }

    /**
     * 尝试 LLM 出题,返回题目内容 Map。失败返回 stub 内容。
     */
    private Map<String, Object> tryLlmGenerate(String knowledgeId, String difficultyLabel) {
        String userPrompt = Prompts.buildQuestionUserPrompt(knowledgeId, difficultyLabel, "");
        try {
            LlmResponse resp = llmService.chat(
                    new LlmRequest(Prompts.QUESTION_GENERATION_SYSTEM_PROMPT, userPrompt));
            Map<String, Object> parsed = parseQuestionJson(resp.content());
            if (parsed != null) {
                parsed.put("_llm_generated", true);
                parsed.put("_model", resp.model());
                return parsed;
            }
        } catch (LlmUnavailableException e) {
            log.info("[QuestionService] LLM 不可用,降级到 stub 出题: {}", e.getMessage());
        } catch (Exception e) {
            log.warn("[QuestionService] LLM 出题失败,降级到 stub: {}", e.getMessage());
        }

        // 降级:stub 内容
        return new HashMap<>(Map.of(
                "prompt", "（待 LLM 出题）",
                "options", List.of("A", "B", "C", "D"),
                "correct_option", "A",
                "_llm_generated", false));
    }

    /**
     * 解析 LLM 返回的题目 JSON。
     */
    private Map<String, Object> parseQuestionJson(String content) {
        try {
            String jsonStr = content;
            if (jsonStr.contains("```json")) {
                jsonStr = jsonStr.substring(jsonStr.indexOf("```json") + 7);
            }
            if (jsonStr.contains("```")) {
                jsonStr = jsonStr.substring(0, jsonStr.indexOf("```"));
            }
            jsonStr = jsonStr.trim();

            JsonNode root = MAPPER.readTree(jsonStr);
            Map<String, Object> result = new HashMap<>();
            result.put("stem", root.path("stem").asText(""));
            result.put("options", MAPPER.convertValue(root.path("options"), List.class));
            result.put("correct_answer", root.path("correct_answer").asText("A"));
            result.put("explanation", root.path("explanation").asText(""));
            result.put("difficulty", root.path("difficulty").asText("medium"));
            return result;
        } catch (Exception e) {
            log.warn("[QuestionService] 题目 JSON 解析失败: {}", e.getMessage());
            return null;
        }
    }

    @Transactional(readOnly = true)
    public Page<Map<String, Object>> listQuestions(BigInteger tenantId, String status,
                                                    String knowledgeId, String questionType,
                                                    Integer difficulty, int limit, int offset) {
        Pageable pageable = PageRequest.of(offset / limit, limit);
        Page<Question> page;
        if (status != null && knowledgeId != null) {
            page = questionRepository.findByTenantIdAndStatusAndKnowledgeId(tenantId, status, knowledgeId, pageable);
        } else if (status != null && questionType != null) {
            page = questionRepository.findByTenantIdAndStatusAndQuestionType(tenantId, status, questionType, pageable);
        } else if (status != null && difficulty != null) {
            page = questionRepository.findByTenantIdAndStatusAndDifficulty(tenantId, status, difficulty, pageable);
        } else if (status != null) {
            page = questionRepository.findByTenantIdAndStatus(tenantId, status, pageable);
        } else if (knowledgeId != null) {
            page = questionRepository.findByTenantIdAndKnowledgeId(tenantId, knowledgeId, pageable);
        } else {
            page = questionRepository.findByTenantId(tenantId, pageable);
        }
        return page.map(q -> toSummaryMap(q));
    }

    @Transactional(readOnly = true)
    public Map<String, Object> getQuestion(BigInteger questionId, boolean includeAnswer) {
        return questionRepository.findById(questionId)
                .map(q -> toDetailMap(q, includeAnswer))
                .orElse(null);
    }

    @Transactional(readOnly = true)
    public String getQuestionStatus(BigInteger questionId) {
        return questionRepository.findById(questionId)
                .map(Question::getStatus)
                .orElse(null);
    }

    @Transactional
    public Map<String, Object> reviewQuestion(BigInteger questionId, String newStatus, Integer reviewerId) {
        if (!VALID_STATUSES.contains(newStatus)) {
            throw new IllegalArgumentException("无效的状态: " + newStatus);
        }
        Question q = questionRepository.findById(questionId)
                .orElse(null);
        if (q == null) return null;
        String current = q.getStatus();
        if (!validTransition(current, newStatus)) {
            throw new IllegalArgumentException(
                    "不允许的状态迁移: " + current + " -> " + newStatus);
        }
        q.setStatus(newStatus);
        q = questionRepository.save(q);
        log.info("Question reviewed: id={} {} -> {} by {}", questionId, current, newStatus, reviewerId);
        return toDetailMap(q, true);
    }

    @Transactional
    public boolean deleteQuestion(BigInteger questionId) {
        return questionRepository.findById(questionId).map(q -> {
            if (!DELETABLE_STATUSES.contains(q.getStatus())) {
                throw new IllegalArgumentException("当前状态不允许删除: " + q.getStatus());
            }
            questionRepository.delete(q);
            return true;
        }).orElse(false);
    }

    @Transactional(readOnly = true)
    public Map<String, Object> verifyAnswer(BigInteger questionId, String studentAnswer) {
        Question q = questionRepository.findById(questionId).orElse(null);
        if (q == null) return null;
        if (!"published".equals(q.getStatus())) {
            throw new IllegalArgumentException("仅 published 题目可校验答案");
        }
        boolean correct = q.getAnswer() != null
                && q.getAnswer().strip().equalsIgnoreCase(studentAnswer.strip());
        Map<String, Object> result = new HashMap<>();
        result.put("question_id", questionId);
        result.put("knowledge_id", q.getKnowledgeId());
        result.put("is_correct", correct);
        result.put("expected_answer", q.getAnswer());
        return result;
    }

    private boolean validTransition(String from, String to) {
        return switch (from) {
            case "draft" -> VALID_TRANSITIONS_FROM_DRAFT.contains(to);
            case "review" -> VALID_TRANSITIONS_FROM_REVIEW.contains(to);
            case "published" -> VALID_TRANSITIONS_FROM_PUBLISHED.contains(to);
            case "rejected" -> VALID_TRANSITIONS_FROM_REJECTED.contains(to);
            case "archived" -> VALID_TRANSITIONS_FROM_ARCHIVED.contains(to);
            default -> false;
        };
    }

    private Map<String, Object> toSummaryMap(Question q) {
        Map<String, Object> m = new HashMap<>();
        m.put("id", q.getId());
        m.put("knowledge_id", q.getKnowledgeId());
        m.put("question_type", q.getQuestionType());
        m.put("difficulty", q.getDifficulty());
        m.put("content", q.getContent());
        m.put("status", q.getStatus());
        m.put("created_by", q.getCreatedBy());
        m.put("created_at", q.getCreatedAt() != null ? q.getCreatedAt().toString() : null);
        m.put("updated_at", q.getUpdatedAt() != null ? q.getUpdatedAt().toString() : null);
        return m;
    }

    private Map<String, Object> toDetailMap(Question q, boolean includeAnswer) {
        Map<String, Object> m = toSummaryMap(q);
        if (includeAnswer) {
            m.put("answer", q.getAnswer());
            m.put("analysis", q.getAnalysis());
        } else {
            m.put("answer", null);
            m.put("analysis", null);
        }
        return m;
    }
}
