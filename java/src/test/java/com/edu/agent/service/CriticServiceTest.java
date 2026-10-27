package com.edu.agent.service;

import com.edu.agent.llm.LlmService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;
import static org.mockito.Mockito.lenient;

/**
 * CriticService 单元测试: 验证启发式评估逻辑(LLM 不可用时的降级)。
 */
@ExtendWith(MockitoExtension.class)
class CriticServiceTest {

    private CriticService criticService;

    @Mock
    private LlmService llmService;

    @BeforeEach
    void setUp() {
        // LLM 不可用 -> 启发式评分降级(lenient 避免 strict 模式报 unnecessary stubbing)
        lenient().when(llmService.chat(any())).thenThrow(new com.edu.agent.llm.LlmUnavailableException("no key"));
        lenient().when(llmService.chatOrFallback(any())).thenReturn(null);
        criticService = new CriticService(llmService);
    }

    @Test
    void evaluate_emptyResponse_lowScoreAndNeedsRegeneration() {
        CriticService.CritiqueResult result = criticService.evaluate(
                "algebra", "beginner", 0.3, false, "", "question");
        assertThat(result).isNotNull();
        assertThat(result.overall()).isLessThanOrEqualTo(3);
        assertThat(result.needsRegeneration()).isTrue();
    }

    @Test
    void evaluate_goodResponse_highScore() {
        String goodResponse = "很好！你在「代数」上的表现不错。当前掌握度：80%。\n" +
                "让我问你一个更深入的问题：你能用自己的话解释一下这个概念吗？\n" +
                "试着想一想,能不能举一个生活中的例子？加油！";
        CriticService.CritiqueResult result = criticService.evaluate(
                "algebra", "proficient", 0.8, true, goodResponse, "question");
        assertThat(result).isNotNull();
        assertThat(result.overall()).isGreaterThanOrEqualTo(3);
        assertThat(result.scores()).containsKeys("pedagogical", "appropriateness", "clarity", "engagement");
    }

    @Test
    void evaluate_scoresInValidRange() {
        CriticService.CritiqueResult result = criticService.evaluate(
                "algebra", "beginner", 0.3, false,
                "让我们一起来思考这个问题,先试着想想已知条件是什么？", "question");
        assertThat(result.scores()).containsKeys("pedagogical", "appropriateness", "clarity", "engagement");
        result.scores().values().forEach(v -> {
            int score = ((Number) v).intValue();
            assertThat(score).isBetween(1, 5);
        });
    }

    @Test
    void evaluate_overallMatchesScoresAverage() {
        CriticService.CritiqueResult result = criticService.evaluate(
                "algebra", "beginner", 0.5, true,
                "不错！试着想一想这个公式是怎么推导出来的？为什么可以这样做？", "question");
        assertThat(result.overall()).isBetween(1, 5);
    }

    @Test
    void regenerate_noLlm_returnsOriginal() {
        String original = "original response";
        CriticService.RegenerationResult result = criticService.regenerate(
                "algebra", "beginner", 0.3, false, original, "critique", "question");
        assertThat(result.text()).isEqualTo(original);
        assertThat(result.metadata()).containsEntry("llm_used", false);
        assertThat(result.metadata()).containsEntry("fallback", "original");
    }

    @Test
    void evaluate_nullResponse_handled() {
        CriticService.CritiqueResult result = criticService.evaluate(
                "algebra", "beginner", 0.3, false, null, "question");
        assertThat(result).isNotNull();
        assertThat(result.needsRegeneration()).isTrue();
    }
}
