package com.edu.agent.llm;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Mock LLM Provider -- 无 API key 时降级用。
 *
 * <p>返回可解析的 JSON(Critic/Question 场景)或固定文本(Tutor/Hint 场景),
 * 标记 {@link #isAvailable()} = false,让调用方走降级逻辑。
 *
 * <p>对齐 Python llm.provider.MockLLMProvider。
 */
@Component
public class MockLlmProvider implements LlmProvider {

    private static final Logger log = LoggerFactory.getLogger(MockLlmProvider.class);

    @Override
    public LlmResponse chat(LlmRequest request) {
        // 根据 system prompt 内容判断场景,返回对应格式的 mock 响应
        String systemPrompt = request.messages().stream()
                .filter(m -> m.role() == Role.SYSTEM)
                .findFirst()
                .map(LlmMessage::content)
                .orElse("")
                .toLowerCase();

        String content;
        if (systemPrompt.contains("critic") || systemPrompt.contains("评审") || systemPrompt.contains("评分")) {
            content = mockCriticJson();
        } else if (systemPrompt.contains("question") || systemPrompt.contains("出题") || systemPrompt.contains("题目")) {
            content = mockQuestionJson();
        } else if (systemPrompt.contains("debate") || systemPrompt.contains("辩论")) {
            content = mockDebateJson();
        } else {
            // Tutor / Hint 场景:返回固定引导文本
            content = "让我们从基础概念开始思考。你能用自己的话解释一下这个知识点的核心含义吗?";
        }

        log.debug("[MockLlmProvider] 返回 mock 响应,场景={}", detectScene(systemPrompt));
        return new LlmResponse(content, "mock", 0, 0, 0, "stop", 0.0);
    }

    private String mockCriticJson() {
        return """
                {
                  "scores": {"pedagogical": 4.0, "appropriateness": 4.5, "clarity": 4.0, "engagement": 3.5},
                  "overall": 4.0,
                  "critique": "该回答结构清晰,概念准确,但可补充具体实例以增强说服力。",
                  "needs_regeneration": false
                }
                """;
    }

    private String mockQuestionJson() {
        return """
                {
                  "stem": "下列哪项最能描述苏格拉底式教学法的核心?",
                  "options": [
                    "A. 直接讲授标准答案",
                    "B. 通过连续提问引导学生自主发现",
                    "C. 让学生反复练习同类题目",
                    "D. 用多媒体展示抽象概念"
                  ],
                  "correct_answer": "B",
                  "explanation": "苏格拉底式教学法(Socratic Method)的核心是通过一系列层层递进的问题,激发学生思考,而非直接给出结论。",
                  "difficulty": "medium",
                  "knowledge_point_id": null
                }
                """;
    }

    private String mockDebateJson() {
        return """
                {
                  "stance": "synthesize",
                  "argument": "综合双方观点:苏格拉底式教学法在培养高阶思维方面具有显著优势,但需要根据学生认知水平灵活调整提问梯度。"
                }
                """;
    }

    private String detectScene(String systemPrompt) {
        if (systemPrompt.contains("critic") || systemPrompt.contains("评审")) return "critic";
        if (systemPrompt.contains("question") || systemPrompt.contains("出题")) return "question";
        if (systemPrompt.contains("debate") || systemPrompt.contains("辩论")) return "debate";
        return "tutor/hint";
    }

    @Override
    public boolean isAvailable() {
        // Mock provider 永远标记为不可用,强制调用方降级
        return false;
    }

    @Override
    public String name() {
        return "mock";
    }
}
