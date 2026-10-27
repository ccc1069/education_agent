package com.edu.agent.agent;

import com.edu.agent.core.AgentEvent;
import com.edu.agent.core.EventType;
import com.edu.agent.service.DebateService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.context.ApplicationEventPublisher;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

/**
 * DebateAgent 单元测试 -- Multi-Agent Debate 触发与综合。
 */
@ExtendWith(MockitoExtension.class)
class DebateAgentTest {

    @Mock
    private ApplicationEventPublisher publisher;

    @Mock
    private DebateService debateService;

    private DebateAgent agent;

    @BeforeEach
    void setUp() {
        agent = new DebateAgent(publisher, debateService);
    }

    @Test
    void handleStudentQuestion_debateModeDisabled_skipped() {
        AgentEvent event = createStudentQuestion("learner1", "algebra", "什么是方程？", false);

        agent.handleStudentQuestion(event);

        verify(debateService, never()).runDebate(any(), any(), anyDouble(), any());
        verify(publisher, never()).publishEvent(any());
    }

    @Test
    void handleStudentQuestion_debateModeEnabled_publishesDebateConsensus() {
        AgentEvent event = createStudentQuestion("learner1", "algebra", "什么是方程？", true);
        mockDebateService("consensus text", "socratic arg", "direct arg", 2);

        agent.handleStudentQuestion(event);

        ArgumentCaptor<AgentEvent> captor = ArgumentCaptor.forClass(AgentEvent.class);
        verify(publisher).publishEvent(captor.capture());

        assertThat(captor.getValue().getType()).isEqualTo(EventType.DEBATE_CONSENSUS);
        assertThat(captor.getValue().getData().get("response")).isEqualTo("consensus text");
    }

    @Test
    void handleStudentQuestion_debateModeEnabled_callsDebateService() {
        AgentEvent event = createStudentQuestion("learner1", "algebra", "什么是方程？", true);
        mockDebateService("consensus", "socratic", "direct", 2);

        agent.handleStudentQuestion(event);

        ArgumentCaptor<String> captor = ArgumentCaptor.forClass(String.class);
        verify(debateService).runDebate(any(), captor.capture(), anyDouble(), any());

        assertThat(captor.getValue()).isEqualTo("beginner");
    }

    @Test
    void handleStudentQuestion_emptyQuestion_skipped() {
        AgentEvent event = createStudentQuestion("learner1", "algebra", "", true);

        agent.handleStudentQuestion(event);

        verify(debateService, never()).runDebate(any(), any(), anyDouble(), any());
        verify(publisher, never()).publishEvent(any());
    }

    @Test
    void handleStudentQuestion_nullQuestion_skipped() {
        AgentEvent event = new AgentEvent(this, EventType.STUDENT_QUESTION, "test", "learner1",
                Map.of("knowledge_id", "algebra", "debate_mode", true));

        agent.handleStudentQuestion(event);

        verify(debateService, never()).runDebate(any(), any(), anyDouble(), any());
        verify(publisher, never()).publishEvent(any());
    }

    @Test
    void handleStudentQuestion_debateReturnsNull_skipped() {
        AgentEvent event = createStudentQuestion("learner1", "algebra", "什么是方程？", true);
        when(debateService.runDebate(any(), any(), anyDouble(), any())).thenReturn(null);

        agent.handleStudentQuestion(event);

        verify(publisher, never()).publishEvent(any());
    }

    @Test
    void handleStudentQuestion_debateReturnsBlankConsensus_skipped() {
        AgentEvent event = createStudentQuestion("learner1", "algebra", "什么是方程？", true);
        mockDebateService("", "socratic", "direct", 2);

        agent.handleStudentQuestion(event);

        verify(publisher, never()).publishEvent(any());
    }

    @Test
    void handleStudentQuestion_payloadContainsAllFields() {
        AgentEvent event = createStudentQuestion("learner1", "algebra", "什么是方程？", true);
        mockDebateService("consensus", "socratic final", "direct final", 3);

        agent.handleStudentQuestion(event);

        ArgumentCaptor<AgentEvent> captor = ArgumentCaptor.forClass(AgentEvent.class);
        verify(publisher).publishEvent(captor.capture());

        Map<String, Object> data = captor.getValue().getData();
        assertThat(data).containsKeys(
                "knowledge_id", "question", "response", "teaching_style",
                "socratic_final", "direct_final", "rounds_completed");
        assertThat(data.get("teaching_style")).isEqualTo("debate_synthesis");
        assertThat(data.get("rounds_completed")).isEqualTo(3);
    }

    private AgentEvent createStudentQuestion(String learnerId, String knowledgeId, String question, boolean debateMode) {
        return new AgentEvent(this, EventType.STUDENT_QUESTION, "test", learnerId,
                Map.of("knowledge_id", knowledgeId, "question", question, "debate_mode", debateMode,
                        "level", "beginner"));
    }

    private void mockDebateService(String consensus, String socratic, String direct, int rounds) {
        DebateService.DebateResult result = new DebateService.DebateResult(
                consensus, socratic, direct, rounds,
                Map.of("llm_used", true, "personas", "socratic,direct"));
        when(debateService.runDebate(any(), any(), anyDouble(), any())).thenReturn(result);
    }
}
