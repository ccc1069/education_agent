package com.edu.agent.service;

import com.edu.agent.llm.LlmService;
import com.edu.agent.llm.LlmUnavailableException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;
import static org.mockito.Mockito.lenient;

/**
 * DebateService 单元测试: 验证启发式辩论综合(LLM 不可用时的降级)。
 */
@ExtendWith(MockitoExtension.class)
class DebateServiceTest {

    private DebateService debateService;

    @Mock
    private LlmService llmService;

    @BeforeEach
    void setUp() {
        lenient().when(llmService.chat(any())).thenThrow(new LlmUnavailableException("no key"));
        debateService = new DebateService(llmService, 2);
    }

    @Test
    void runDebate_returnsConsensus() {
        DebateService.DebateResult result = debateService.runDebate(
                "algebra", "beginner", 0.3, "什么是方程？");
        assertThat(result).isNotNull();
        assertThat(result.consensus()).isNotBlank();
        assertThat(result.consensus()).contains("方程");
    }

    @Test
    void runDebate_returnsBothPersonas() {
        DebateService.DebateResult result = debateService.runDebate(
                "algebra", "beginner", 0.3, "什么是方程？");
        assertThat(result.socraticFinal()).isNotBlank();
        assertThat(result.directFinal()).isNotBlank();
    }

    @Test
    void runDebate_roundsCompletedMatchesConfig() {
        DebateService.DebateResult result = debateService.runDebate(
                "algebra", "beginner", 0.3, "什么是方程？");
        assertThat(result.roundsCompleted()).isEqualTo(2);
    }

    @Test
    void runDebate_metadataContainsPersonas() {
        DebateService.DebateResult result = debateService.runDebate(
                "algebra", "beginner", 0.3, "什么是方程？");
        assertThat(result.metadata()).containsKey("personas");
        assertThat(result.metadata()).containsEntry("llm_used", false);
    }

    @Test
    void runDebate_respectsMaxRounds() {
        DebateService service = new DebateService(llmService, 10);
        DebateService.DebateResult result = service.runDebate(
                "algebra", "beginner", 0.3, "什么是方程？");
        assertThat(result.roundsCompleted()).isLessThanOrEqualTo(4); // MAX_ROUNDS = 4
    }

    @Test
    void runDebate_minRoundsIsOne() {
        DebateService service = new DebateService(llmService, 0);
        DebateService.DebateResult result = service.runDebate(
                "algebra", "beginner", 0.3, "什么是方程？");
        assertThat(result.roundsCompleted()).isGreaterThanOrEqualTo(1);
    }
}
