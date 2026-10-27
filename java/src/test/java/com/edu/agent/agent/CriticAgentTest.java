package com.edu.agent.agent;

import com.edu.agent.core.AgentEvent;
import com.edu.agent.core.EventType;
import com.edu.agent.db.entity.Critique;
import com.edu.agent.db.repository.CritiqueRepository;
import com.edu.agent.service.CriticService;
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
import static org.mockito.Mockito.lenient;

/**
 * CriticAgent 单元测试 -- LLM-as-judge 评估 + 自反思再生成。
 */
@ExtendWith(MockitoExtension.class)
class CriticAgentTest {

    @Mock
    private ApplicationEventPublisher publisher;

    @Mock
    private CriticService criticService;

    @Mock
    private CritiqueRepository critiqueRepository;

    private CriticAgent agent;

    @BeforeEach
    void setUp() {
        agent = new CriticAgent(publisher, criticService, critiqueRepository);
    }

    @Test
    void handleTeachingResponse_publishesTeachingCriticized() {
        AgentEvent event = createTeachingResponse("learner1", "algebra", "good response", "proficient");
        mockCriticService(4, false);

        agent.handleTeachingResponse(event);

        ArgumentCaptor<AgentEvent> captor = ArgumentCaptor.forClass(AgentEvent.class);
        verify(publisher).publishEvent(captor.capture());

        assertThat(captor.getValue().getType()).isEqualTo(EventType.TEACHING_CRITICIZED);
        assertThat(captor.getValue().getData()).containsKey("overall");
        assertThat(captor.getValue().getData()).containsKey("scores");
    }

    @Test
    void handleTeachingResponse_savesCritiqueEntity() {
        AgentEvent event = createTeachingResponse("learner1", "algebra", "response", "beginner");
        mockCriticService(3, false);

        agent.handleTeachingResponse(event);

        ArgumentCaptor<Critique> captor = ArgumentCaptor.forClass(Critique.class);
        verify(critiqueRepository).save(captor.capture());

        Critique saved = captor.getValue();
        assertThat(saved.getLearnerId()).isEqualTo("learner1");
        assertThat(saved.getKnowledgeId()).isEqualTo("algebra");
        assertThat(saved.getOverall()).isEqualTo((short) 3);
    }

    @Test
    void handleTeachingResponse_lowScore_triggersRegeneration() {
        AgentEvent event = createTeachingResponse("learner1", "algebra", "bad response", "beginner");
        mockCriticService(2, true); // needs regeneration

        agent.handleTeachingResponse(event);

        // Should publish TEACHING_CRITICIZED + TEACHING_RESPONSE (regenerated)
        ArgumentCaptor<AgentEvent> captor = ArgumentCaptor.forClass(AgentEvent.class);
        verify(publisher, atLeast(2)).publishEvent(captor.capture());

        assertThat(captor.getAllValues())
                .anyMatch(e -> e.getType() == EventType.TEACHING_RESPONSE
                        && Boolean.TRUE.equals(e.getData().get("regenerated")));
    }

    @Test
    void handleTeachingResponse_hintStyle_skipped() {
        AgentEvent event = new AgentEvent(this, EventType.TEACHING_RESPONSE, "TutorAgent", "learner1",
                Map.of("knowledge_id", "algebra", "response", "hint text", "teaching_style", "hint"));

        agent.handleTeachingResponse(event);

        verify(criticService, never()).evaluate(any(), any(), anyDouble(), any(), any(), any());
        verify(publisher, never()).publishEvent(any());
    }

    @Test
    void handleTeachingResponse_regenerated_skipped() {
        AgentEvent event = new AgentEvent(this, EventType.TEACHING_RESPONSE, "CriticAgent", "learner1",
                Map.of("knowledge_id", "algebra", "response", "regenerated response", "regenerated", true));

        agent.handleTeachingResponse(event);

        verify(criticService, never()).evaluate(any(), any(), anyDouble(), any(), any(), any());
        verify(publisher, never()).publishEvent(any());
    }

    @Test
    void handleTeachingResponse_noLoopOnRegeneration() {
        AgentEvent event = createTeachingResponse("learner1", "algebra", "bad", "beginner");
        mockCriticService(2, true);

        // First call triggers regeneration
        agent.handleTeachingResponse(event);

        // Clear invocation count
        clearInvocations(publisher);

        // Second call with same event (simulating re-entrant) should be skipped if regenerated
        AgentEvent regeneratedEvent = new AgentEvent(this, EventType.TEACHING_RESPONSE, "CriticAgent",
                "learner1",
                Map.of("knowledge_id", "algebra", "response", "regenerated", "regenerated", true));
        agent.handleTeachingResponse(regeneratedEvent);

        verify(publisher, never()).publishEvent(any());
    }

    private AgentEvent createTeachingResponse(String learnerId, String knowledgeId, String response, String level) {
        return new AgentEvent(this, EventType.TEACHING_RESPONSE, "TutorAgent", learnerId,
                Map.of("knowledge_id", knowledgeId, "response", response,
                        "difficulty_level", level, "teaching_style", "socratic"));
    }

    private void mockCriticService(int overall, boolean needsRegeneration) {
        Map<String, Object> scores = Map.of(
                "pedagogical", 3.0, "appropriateness", 3.0, "clarity", 3.0, "engagement", 3.0);
        CriticService.CritiqueResult result = new CriticService.CritiqueResult(
                scores, overall, "critique text", needsRegeneration, "heuristic", 0);
        when(criticService.evaluate(any(), any(), anyDouble(), any(), any(), any())).thenReturn(result);

        CriticService.RegenerationResult regenResult = new CriticService.RegenerationResult(
                "improved response", Map.of("llm_used", false, "regenerated", true));
        lenient().when(criticService.regenerate(any(), any(), anyDouble(), any(), any(), any(), any()))
                .thenReturn(regenResult);
    }
}
