package com.edu.agent.agent;

import com.edu.agent.core.AgentEvent;
import com.edu.agent.core.EventType;
import com.edu.agent.core.LearnerModel;
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
 * AssessmentAgent 单元测试 -- BKT 知识追踪评估逻辑。
 */
@ExtendWith(MockitoExtension.class)
class AssessmentAgentTest {

    @Mock
    private ApplicationEventPublisher publisher;

    private AssessmentAgent agent;

    @BeforeEach
    void setUp() {
        agent = new AssessmentAgent(publisher, com.edu.agent.service.LearnerModelService.inMemoryOnly());
    }

    @Test
    void handleSubmission_firstCorrectAnswer_increasesMastery() {
        AgentEvent event = createSubmission("learner1", "algebra", true);
        agent.handleSubmission(event);

        LearnerModel model = agent.getLearnerModels().get("learner1");
        assertThat(model).isNotNull();
        assertThat(model.getState("algebra").getMastery()).isGreaterThan(0.1); // P_INIT
        assertThat(model.getState("algebra").getAttempts()).isEqualTo(1);
    }

    @Test
    void handleSubmission_multipleCorrectAnswers_masteryIncreases() {
        String learner = "learner1";
        String kp = "algebra";
        for (int i = 0; i < 5; i++) {
            agent.handleSubmission(createSubmission(learner, kp, true));
        }

        LearnerModel.KnowledgeState state = agent.getLearnerModels().get(learner).getState(kp);
        assertThat(state.getMastery()).isGreaterThan(0.5);
        assertThat(state.getAttempts()).isEqualTo(5);
        assertThat(state.getLevel()).isIn("proficient", "mastered");
    }

    @Test
    void handleSubmission_wrongAnswer_doesNotIncreaseMastery() {
        String learner = "learner1";
        String kp = "algebra";
        // First correct to build some mastery
        agent.handleSubmission(createSubmission(learner, kp, true));
        double masteryAfterCorrect = agent.getLearnerModels().get(learner).getState(kp).getMastery();

        // Then wrong
        agent.handleSubmission(createSubmission(learner, kp, false));
        double masteryAfterWrong = agent.getLearnerModels().get(learner).getState(kp).getMastery();

        assertThat(masteryAfterWrong).isLessThan(masteryAfterCorrect);
    }

    @Test
    void handleSubmission_publishesMasteryUpdated() {
        AgentEvent event = createSubmission("learner1", "algebra", true);
        agent.handleSubmission(event);

        ArgumentCaptor<AgentEvent> captor = ArgumentCaptor.forClass(AgentEvent.class);
        verify(publisher, atLeast(1)).publishEvent(captor.capture());

        // Should publish MASTERY_UPDATED
        assertThat(captor.getAllValues())
                .anyMatch(e -> e.getType() == EventType.MASTERY_UPDATED);
    }

    @Test
    void handleSubmission_publishesAssessmentComplete() {
        AgentEvent event = createSubmission("learner1", "algebra", true);
        agent.handleSubmission(event);

        ArgumentCaptor<AgentEvent> captor = ArgumentCaptor.forClass(AgentEvent.class);
        verify(publisher, atLeast(1)).publishEvent(captor.capture());

        assertThat(captor.getAllValues())
                .anyMatch(e -> e.getType() == EventType.ASSESSMENT_COMPLETE);
    }

    @Test
    void handleSubmission_lowMasteryAfterManyAttempts_publishesWeaknessDetected() {
        String learner = "learner1";
        String kp = "weak_kp";
        // 3+ wrong answers with mastery < 0.3
        for (int i = 0; i < 4; i++) {
            agent.handleSubmission(createSubmission(learner, kp, false));
        }

        ArgumentCaptor<AgentEvent> captor = ArgumentCaptor.forClass(AgentEvent.class);
        verify(publisher, atLeast(1)).publishEvent(captor.capture());

        assertThat(captor.getAllValues())
                .anyMatch(e -> e.getType() == EventType.WEAKNESS_DETECTED);
    }

    @Test
    void handleSubmission_multipleLearners_isolated() {
        agent.handleSubmission(createSubmission("learner1", "algebra", true));
        agent.handleSubmission(createSubmission("learner2", "algebra", false));

        assertThat(agent.getLearnerModels()).hasSize(2);
        assertThat(agent.getLearnerModels().get("learner1").getState("algebra").getMastery())
                .isGreaterThan(agent.getLearnerModels().get("learner2").getState("algebra").getMastery());
    }

    @Test
    void handleSubmission_levelAssignment_correct() {
        String learner = "learner1";
        String kp = "algebra";
        // Many correct answers -> high mastery
        for (int i = 0; i < 10; i++) {
            agent.handleSubmission(createSubmission(learner, kp, true));
        }
        String level = agent.getLearnerModels().get(learner).getState(kp).getLevel();
        assertThat(level).isIn("proficient", "mastered");
    }

    private AgentEvent createSubmission(String learnerId, String knowledgeId, boolean isCorrect) {
        return new AgentEvent(this, EventType.STUDENT_SUBMISSION, "test", learnerId,
                Map.of("knowledge_id", knowledgeId, "is_correct", isCorrect));
    }
}
