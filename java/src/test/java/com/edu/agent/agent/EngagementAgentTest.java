package com.edu.agent.agent;

import com.edu.agent.core.AgentEvent;
import com.edu.agent.core.EventType;
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
 * EngagementAgent 单元测试 -- 6 种学习状态检测与自适应干预。
 */
@ExtendWith(MockitoExtension.class)
class EngagementAgentTest {

    @Mock
    private ApplicationEventPublisher publisher;

    private EngagementAgent agent;

    @BeforeEach
    void setUp() {
        agent = new EngagementAgent(publisher);
    }

    @Test
    void trackSubmission_recordsCorrectAnswer() {
        AgentEvent event = createSubmission("learner1", true, 30.0);
        agent.trackSubmission(event);

        // No direct assertion on state, but should not throw
        verify(publisher, never()).publishEvent(any()); // trackSubmission doesn't publish
    }

    @Test
    void analyzeEngagement_consecutiveErrors_triggersFrustration() {
        String learner = "learner1";
        // 3 consecutive errors
        for (int i = 0; i < 3; i++) {
            agent.trackSubmission(createSubmission(learner, false, 10.0));
        }

        // Now trigger assessment
        AgentEvent assessment = new AgentEvent(this, EventType.ASSESSMENT_COMPLETE, "test", learner,
                Map.of());
        agent.analyzeEngagement(assessment);

        ArgumentCaptor<AgentEvent> captor = ArgumentCaptor.forClass(AgentEvent.class);
        verify(publisher, atLeast(1)).publishEvent(captor.capture());

        assertThat(captor.getAllValues())
                .anyMatch(e -> e.getType() == EventType.ENGAGEMENT_ALERT
                        && "frustration".equals(e.getData().get("alert_type")));
    }

    @Test
    void analyzeEngagement_consecutiveCorrect_triggersBoredom() {
        String learner = "learner1";
        // 5+ consecutive correct with high accuracy
        for (int i = 0; i < 6; i++) {
            agent.trackSubmission(createSubmission(learner, true, 5.0));
        }

        AgentEvent assessment = new AgentEvent(this, EventType.ASSESSMENT_COMPLETE, "test", learner,
                Map.of());
        agent.analyzeEngagement(assessment);

        ArgumentCaptor<AgentEvent> captor = ArgumentCaptor.forClass(AgentEvent.class);
        verify(publisher, atLeast(1)).publishEvent(captor.capture());

        assertThat(captor.getAllValues())
                .anyMatch(e -> e.getType() == EventType.ENGAGEMENT_ALERT
                        && "boredom".equals(e.getData().get("alert_type")));
    }

    @Test
    void analyzeEngagement_frustration_triggersPaceAdjustment() {
        String learner = "learner1";
        for (int i = 0; i < 3; i++) {
            agent.trackSubmission(createSubmission(learner, false, 10.0));
        }

        AgentEvent assessment = new AgentEvent(this, EventType.ASSESSMENT_COMPLETE, "test", learner,
                Map.of());
        agent.analyzeEngagement(assessment);

        ArgumentCaptor<AgentEvent> captor = ArgumentCaptor.forClass(AgentEvent.class);
        verify(publisher, atLeast(1)).publishEvent(captor.capture());

        assertThat(captor.getAllValues())
                .anyMatch(e -> e.getType() == EventType.PACE_ADJUSTMENT
                        && "slow_down".equals(e.getData().get("action")));
    }

    @Test
    void analyzeEngagement_boredom_triggersSpeedUp() {
        String learner = "learner1";
        for (int i = 0; i < 6; i++) {
            agent.trackSubmission(createSubmission(learner, true, 5.0));
        }

        AgentEvent assessment = new AgentEvent(this, EventType.ASSESSMENT_COMPLETE, "test", learner,
                Map.of());
        agent.analyzeEngagement(assessment);

        ArgumentCaptor<AgentEvent> captor = ArgumentCaptor.forClass(AgentEvent.class);
        verify(publisher, atLeast(1)).publishEvent(captor.capture());

        assertThat(captor.getAllValues())
                .anyMatch(e -> e.getType() == EventType.PACE_ADJUSTMENT
                        && "speed_up".equals(e.getData().get("action")));
    }

    @Test
    void analyzeEngagement_focusedState_noAlert() {
        String learner = "learner1";
        // Mixed results -> focused (not bored, not frustrated)
        agent.trackSubmission(createSubmission(learner, true, 10.0));
        agent.trackSubmission(createSubmission(learner, false, 10.0));
        agent.trackSubmission(createSubmission(learner, true, 10.0));

        AgentEvent assessment = new AgentEvent(this, EventType.ASSESSMENT_COMPLETE, "test", learner,
                Map.of());
        agent.analyzeEngagement(assessment);

        ArgumentCaptor<AgentEvent> captor = ArgumentCaptor.forClass(AgentEvent.class);
        verify(publisher, atLeast(0)).publishEvent(captor.capture());

        // No ENGAGEMENT_ALERT for focused state
        assertThat(captor.getAllValues())
                .noneMatch(e -> e.getType() == EventType.ENGAGEMENT_ALERT);
    }

    @Test
    void analyzeEngagement_noStateChange_noEvent() {
        String learner = "learner1";
        // Single submission, state likely stays FOCUSED
        agent.trackSubmission(createSubmission(learner, true, 10.0));

        AgentEvent assessment = new AgentEvent(this, EventType.ASSESSMENT_COMPLETE, "test", learner,
                Map.of());
        agent.analyzeEngagement(assessment);

        // If state didn't change, no events published
        verify(publisher, never()).publishEvent(any());
    }

    @Test
    void analyzeEngagement_multipleLearners_isolated() {
        String learner1 = "learner1";
        String learner2 = "learner2";

        for (int i = 0; i < 3; i++) {
            agent.trackSubmission(createSubmission(learner1, false, 10.0));
        }
        agent.trackSubmission(createSubmission(learner2, true, 10.0));

        // Only learner1 should be frustrated
        AgentEvent assessment1 = new AgentEvent(this, EventType.ASSESSMENT_COMPLETE, "test", learner1,
                Map.of());
        agent.analyzeEngagement(assessment1);

        ArgumentCaptor<AgentEvent> captor = ArgumentCaptor.forClass(AgentEvent.class);
        verify(publisher, atLeast(1)).publishEvent(captor.capture());

        assertThat(captor.getAllValues())
                .anyMatch(e -> e.getLearnerId().equals(learner1) && e.getType() == EventType.ENGAGEMENT_ALERT);
    }

    private AgentEvent createSubmission(String learnerId, boolean isCorrect, double timeSpent) {
        return new AgentEvent(this, EventType.STUDENT_SUBMISSION, "test", learnerId,
                Map.of("knowledge_id", "algebra", "is_correct", isCorrect, "time_spent_seconds", timeSpent));
    }
}
