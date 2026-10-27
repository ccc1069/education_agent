package com.edu.agent.agent;

import com.edu.agent.core.AgentEvent;
import com.edu.agent.core.EventType;
import com.edu.agent.core.KnowledgeGraph;
import com.edu.agent.core.SpacedRepetition;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.context.ApplicationEventPublisher;

import java.util.Map;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

/**
 * CurriculumAgent 单元测试 -- SM-2 间隔重复 + 知识图谱学习路径。
 */
@ExtendWith(MockitoExtension.class)
class CurriculumAgentTest {

    @Mock
    private ApplicationEventPublisher publisher;

    private CurriculumAgent agent;

    @BeforeEach
    void setUp() {
        agent = new CurriculumAgent(publisher);
    }

    @Test
    void handleMasteryUpdate_publishesReviewScheduled() {
        AgentEvent event = createMasteryUpdate("learner1", "algebra", 0.5);
        agent.handleMasteryUpdate(event);

        ArgumentCaptor<AgentEvent> captor = ArgumentCaptor.forClass(AgentEvent.class);
        verify(publisher, atLeast(1)).publishEvent(captor.capture());

        assertThat(captor.getAllValues())
                .anyMatch(e -> e.getType() == EventType.REVIEW_SCHEDULED);
    }

    @Test
    void handleMasteryUpdate_highMastery_publishesNextTopic() {
        // mastery >= 0.6 triggers next topic recommendation
        AgentEvent event = createMasteryUpdate("learner1", "arithmetic", 0.95);
        agent.handleMasteryUpdate(event);

        ArgumentCaptor<AgentEvent> captor = ArgumentCaptor.forClass(AgentEvent.class);
        verify(publisher, atLeast(1)).publishEvent(captor.capture());

        assertThat(captor.getAllValues())
                .anyMatch(e -> e.getType() == EventType.NEXT_TOPIC);
    }

    @Test
    void handleMasteryUpdate_lowMastery_noNextTopic() {
        AgentEvent event = createMasteryUpdate("learner1", "algebra", 0.3);
        agent.handleMasteryUpdate(event);

        ArgumentCaptor<AgentEvent> captor = ArgumentCaptor.forClass(AgentEvent.class);
        verify(publisher, atLeast(1)).publishEvent(captor.capture());

        assertThat(captor.getAllValues())
                .noneMatch(e -> e.getType() == EventType.NEXT_TOPIC);
    }

    @Test
    void handleWeakness_publishesPathUpdated() {
        AgentEvent event = new AgentEvent(this, EventType.WEAKNESS_DETECTED, "test", "learner1",
                Map.of("knowledge_id", "quadratic_eq"));
        agent.handleWeakness(event);

        ArgumentCaptor<AgentEvent> captor = ArgumentCaptor.forClass(AgentEvent.class);
        verify(publisher).publishEvent(captor.capture());

        AgentEvent published = captor.getValue();
        assertThat(published.getType()).isEqualTo(EventType.PATH_UPDATED);
        assertThat(published.getData()).containsKey("remedial_path");
    }

    @Test
    void handleWeakness_remedialPathContainsPrerequisites() {
        AgentEvent event = new AgentEvent(this, EventType.WEAKNESS_DETECTED, "test", "learner1",
                Map.of("knowledge_id", "quadratic_eq"));
        agent.handleWeakness(event);

        ArgumentCaptor<AgentEvent> captor = ArgumentCaptor.forClass(AgentEvent.class);
        verify(publisher).publishEvent(captor.capture());

        @SuppressWarnings("unchecked")
        java.util.List<String> path = (java.util.List<String>) captor.getValue().getData().get("remedial_path");
        assertThat(path).isNotEmpty();
        // quadratic_eq requires factoring, linear_eq_1, algebraic_expr, etc.
        assertThat(path).contains("quadratic_eq");
    }

    @Test
    void handlePaceAdjustment_doesNotPublish() {
        AgentEvent event = new AgentEvent(this, EventType.PACE_ADJUSTMENT, "test", "learner1",
                Map.of("action", "slow_down", "reason", "frustration"));
        agent.handlePaceAdjustment(event);

        // PACE_ADJUSTMENT handler only logs, does not publish
        verify(publisher, never()).publishEvent(any());
    }

    @Test
    void knowledgeGraph_topologicalSort_valid() {
        KnowledgeGraph graph = KnowledgeGraph.buildSampleMathGraph();
        java.util.List<String> sorted = graph.topologicalSort();
        assertThat(sorted).hasSize(20);

        // arithmetic should come before fractions
        assertThat(sorted.indexOf("arithmetic")).isLessThan(sorted.indexOf("fractions"));
        // linear_eq_1 should come before quadratic_eq
        assertThat(sorted.indexOf("linear_eq_1")).isLessThan(sorted.indexOf("quadratic_eq"));
    }

    @Test
    void knowledgeGraph_getReadyNodes_returnsLearnableNodes() {
        KnowledgeGraph graph = KnowledgeGraph.buildSampleMathGraph();
        Set<String> mastered = Set.of("arithmetic");
        java.util.List<String> ready = graph.getReadyNodes(mastered);

        // fractions, negative_numbers, sets are ready after arithmetic
        assertThat(ready).contains("fractions", "negative_numbers", "sets");
        // algebraic_expr requires both arithmetic AND negative_numbers
        assertThat(ready).doesNotContain("algebraic_expr");
    }

    @Test
    void spacedRepetition_review_increasesInterval() {
        SpacedRepetition sr = new SpacedRepetition();
        SpacedRepetition.ReviewItem item = new SpacedRepetition.ReviewItem("algebra");

        sr.review(item, 5); // perfect
        assertThat(item.getIntervalDays()).isEqualTo(1);

        sr.review(item, 5);
        assertThat(item.getIntervalDays()).isEqualTo(6);

        sr.review(item, 5);
        assertThat(item.getIntervalDays()).isGreaterThan(6);
    }

    @Test
    void spacedRepetition_lowQuality_resetsInterval() {
        SpacedRepetition sr = new SpacedRepetition();
        SpacedRepetition.ReviewItem item = new SpacedRepetition.ReviewItem("algebra");

        sr.review(item, 5);
        sr.review(item, 5);
        double intervalBefore = item.getIntervalDays();

        sr.review(item, 1); // poor quality
        assertThat(item.getIntervalDays()).isLessThan(intervalBefore);
        assertThat(item.getRepetition()).isEqualTo(0);
    }

    private AgentEvent createMasteryUpdate(String learnerId, String knowledgeId, double mastery) {
        return new AgentEvent(this, EventType.MASTERY_UPDATED, "test", learnerId,
                Map.of("knowledge_id", knowledgeId, "mastery", mastery));
    }
}
