package agent

import (
	"testing"
	"time"

	"multi-agent-education/golang/internal/eventbus"
	"multi-agent-education/golang/internal/llm"
	"multi-agent-education/golang/internal/question"
)

func TestQuestionAgent_OnWrongAnswer_GeneratesQuestion(t *testing.T) {
	bus := eventbus.New()
	bank := question.NewQuestionBank()
	llmSvc := llm.NewLlmService(llm.NewMockLlmProvider())
	questionSvc := question.NewQuestionService(llmSvc, bank)

	// 先注册收集器
	var published []eventbus.Event
	bus.Subscribe(eventbus.QuestionGenerated, func(e eventbus.Event) {
		published = append(published, e)
	})

	agent := NewQuestionAgent(bus, bank, questionSvc)
	go agent.Start()

	// 等待 Agent 完成订阅注册
	time.Sleep(100 * time.Millisecond)

	// 发布错误答题事件
	bus.Publish(eventbus.Event{
		Type:      eventbus.StudentSubmission,
		Source:    "test",
		LearnerID: "learner-001",
		Data: map[string]interface{}{
			"is_correct":   false,
			"knowledge_id": "pythagorean",
		},
	})

	// 等待处理
	time.Sleep(500 * time.Millisecond)

	if len(published) == 0 {
		t.Error("QuestionAgent should publish QuestionGenerated event on wrong answer")
	}
}

func TestQuestionAgent_OnCorrectAnswer_Skips(t *testing.T) {
	bus := eventbus.New()
	bank := question.NewQuestionBank()
	llmSvc := llm.NewLlmService(llm.NewMockLlmProvider())
	questionSvc := question.NewQuestionService(llmSvc, bank)

	var published []eventbus.Event
	bus.Subscribe(eventbus.QuestionGenerated, func(e eventbus.Event) {
		published = append(published, e)
	})

	agent := NewQuestionAgent(bus, bank, questionSvc)
	go agent.Start()

	time.Sleep(100 * time.Millisecond)

	// 发布正确答题事件
	bus.Publish(eventbus.Event{
		Type:      eventbus.StudentSubmission,
		Source:    "test",
		LearnerID: "learner-001",
		Data: map[string]interface{}{
			"is_correct":   true,
			"knowledge_id": "pythagorean",
		},
	})

	time.Sleep(300 * time.Millisecond)

	if len(published) != 0 {
		t.Error("QuestionAgent should skip correct answers")
	}
}

func TestQuestionAgent_MissingKnowledgeID_Skips(t *testing.T) {
	bus := eventbus.New()
	bank := question.NewQuestionBank()
	llmSvc := llm.NewLlmService(llm.NewMockLlmProvider())
	questionSvc := question.NewQuestionService(llmSvc, bank)

	var published []eventbus.Event
	bus.Subscribe(eventbus.QuestionGenerated, func(e eventbus.Event) {
		published = append(published, e)
	})

	agent := NewQuestionAgent(bus, bank, questionSvc)
	go agent.Start()

	time.Sleep(100 * time.Millisecond)

	// 发布缺少 knowledge_id 的事件
	bus.Publish(eventbus.Event{
		Type:      eventbus.StudentSubmission,
		Source:    "test",
		LearnerID: "learner-001",
		Data: map[string]interface{}{
			"is_correct": false,
		},
	})

	time.Sleep(300 * time.Millisecond)

	if len(published) != 0 {
		t.Error("QuestionAgent should skip events without knowledge_id")
	}
}
