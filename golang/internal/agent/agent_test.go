package agent

import (
	"context"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"multi-agent-education/golang/internal/eventbus"
	"multi-agent-education/golang/internal/llm"
	"multi-agent-education/golang/internal/persist"
)

// ─── fakeProvider: 始终失败的 provider(测试降级) ───

type fakeProvider struct{}

func (p *fakeProvider) Chat(ctx context.Context, req llm.LlmRequest) (llm.LlmResponse, error) {
	return llm.ErrorResponse("fake provider always fails"), &llm.LlmUnavailableError{
		Message: "fake", Retryable: true,
	}
}

func (p *fakeProvider) IsAvailable() bool { return true }
func (p *fakeProvider) Name() string       { return "fake" }

// ─── 辅助: 收集事件的订阅者 ───

type eventCollector struct {
	mu     sync.Mutex
	events []eventbus.Event
}

func (c *eventCollector) handler(e eventbus.Event) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.events = append(c.events, e)
}

func (c *eventCollector) getEvents() []eventbus.Event {
	c.mu.Lock()
	defer c.mu.Unlock()
	result := make([]eventbus.Event, len(c.events))
	copy(result, c.events)
	return result
}

func (c *eventCollector) countByType(t eventbus.EventType) int {
	c.mu.Lock()
	defer c.mu.Unlock()
	count := 0
	for _, e := range c.events {
		if e.Type == t {
			count++
		}
	}
	return count
}

// ─── CriticAgent 测试 ───

func TestCriticAgent_SkipsRegeneratedEvents(t *testing.T) {
	bus := eventbus.New()
	collector := &eventCollector{}
	bus.Subscribe(eventbus.TeachingCriticized, collector.handler)

	llmService := llm.NewLlmServiceWithConfig(&fakeProvider{}, 1, 0, 5, time.Minute)
	agent := NewCriticAgent(bus, llmService)
	agent.Start()

	// 发布 regenerated=true 的事件 -- 应被跳过
	bus.Publish(eventbus.Event{
		Type: eventbus.TeachingResponse, Source: "TutorAgent",
		LearnerID: "learner1",
		Data: map[string]interface{}{
			"knowledge_id":   "algebra",
			"response":       "test response",
			"regenerated":    true,
			"teaching_style": "socratic",
		},
	})

	time.Sleep(100 * time.Millisecond)

	if collector.countByType(eventbus.TeachingCriticized) != 0 {
		t.Errorf("CriticAgent should skip regenerated events, got %d TeachingCriticized events",
			collector.countByType(eventbus.TeachingCriticized))
	}
}

func TestCriticAgent_SkipsHintEvents(t *testing.T) {
	bus := eventbus.New()
	collector := &eventCollector{}
	bus.Subscribe(eventbus.TeachingCriticized, collector.handler)

	llmService := llm.NewLlmServiceWithConfig(&fakeProvider{}, 1, 0, 5, time.Minute)
	agent := NewCriticAgent(bus, llmService)
	agent.Start()

	// 发布 teaching_style=hint 的事件 -- 应被跳过
	bus.Publish(eventbus.Event{
		Type: eventbus.TeachingResponse, Source: "TutorAgent",
		LearnerID: "learner1",
		Data: map[string]interface{}{
			"knowledge_id":   "algebra",
			"response":       "hint text",
			"teaching_style": "hint",
		},
	})

	time.Sleep(100 * time.Millisecond)

	if collector.countByType(eventbus.TeachingCriticized) != 0 {
		t.Errorf("CriticAgent should skip hint events, got %d TeachingCriticized events",
			collector.countByType(eventbus.TeachingCriticized))
	}
}

func TestCriticAgent_EvaluatesAndPublishesCriticized(t *testing.T) {
	bus := eventbus.New()
	collector := &eventCollector{}
	bus.Subscribe(eventbus.TeachingCriticized, collector.handler)

	llmService := llm.NewLlmServiceWithConfig(&fakeProvider{}, 1, 0, 5, time.Minute)
	agent := NewCriticAgent(bus, llmService)
	agent.Start()

	// 发布正常教学回复事件
	bus.Publish(eventbus.Event{
		Type: eventbus.TeachingResponse, Source: "TutorAgent",
		LearnerID: "learner1",
		Data: map[string]interface{}{
			"knowledge_id":   "algebra",
			"response":       "很好！让我们一起来分析这个问题。试着想想用已知条件能推导出什么？",
			"teaching_style": "socratic",
			"difficulty_level": "developing",
			"mastery":        0.5,
		},
	})

	time.Sleep(200 * time.Millisecond)

	// 验证发布了 TeachingCriticized 事件
	criticizedEvents := collector.countByType(eventbus.TeachingCriticized)
	if criticizedEvents != 1 {
		t.Errorf("expected 1 TeachingCriticized event, got %d", criticizedEvents)
	}

	events := collector.getEvents()
	if len(events) != 1 {
		t.Fatalf("expected 1 event, got %d", len(events))
	}

	// 验证事件内容
	if events[0].Data["knowledge_id"] != "algebra" {
		t.Errorf("expected knowledge_id=algebra, got %v", events[0].Data["knowledge_id"])
	}
	if _, ok := events[0].Data["overall"]; !ok {
		t.Error("expected 'overall' field in TeachingCriticized event")
	}
	if _, ok := events[0].Data["scores"]; !ok {
		t.Error("expected 'scores' field in TeachingCriticized event")
	}
}

func TestCriticAgent_RegeneratesOnLowScore(t *testing.T) {
	bus := eventbus.New()
	collector := &eventCollector{}
	bus.Subscribe(eventbus.TeachingResponse, collector.handler)

	llmService := llm.NewLlmServiceWithConfig(&fakeProvider{}, 1, 0, 5, time.Minute)
	agent := NewCriticAgent(bus, llmService)
	agent.Start()

	// 发布一个低质量回复(短文本,无提问,无鼓励) -- 启发式评分应 <= 3.0
	bus.Publish(eventbus.Event{
		Type: eventbus.TeachingResponse, Source: "TutorAgent",
		LearnerID: "learner1",
		Data: map[string]interface{}{
			"knowledge_id":   "algebra",
			"response":       "ok",
			"teaching_style": "socratic",
			"difficulty_level": "beginner",
			"mastery":        0.2,
		},
	})

	time.Sleep(300 * time.Millisecond)

	// 验证发布了 regenerated=true 的 TeachingResponse
	regenCount := 0
	for _, e := range collector.getEvents() {
		if regen, ok := e.Data["regenerated"].(bool); ok && regen {
			regenCount++
		}
	}
	if regenCount != 1 {
		t.Errorf("expected 1 regenerated TeachingResponse, got %d", regenCount)
	}
}

func TestCriticAgent_PersistsCritique(t *testing.T) {
	dir := t.TempDir()
	db, err := persist.Open(filepath.Join(dir, "edu.db"))
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	defer db.Close()

	bus := eventbus.New()
	llmService := llm.NewLlmServiceWithConfig(&fakeProvider{}, 1, 0, 5, time.Minute)
	agent := NewCriticAgent(bus, llmService)
	agent.SetPersist(db)
	agent.Start()

	bus.Publish(eventbus.Event{
		ID: "teach-evt-persist", Type: eventbus.TeachingResponse, Source: "TutorAgent",
		LearnerID: "learner1",
		Data: map[string]interface{}{
			"knowledge_id":     "algebra",
			"response":         "ok",
			"teaching_style":   "socratic",
			"difficulty_level": "beginner",
		},
	})
	time.Sleep(300 * time.Millisecond)

	n, err := db.CountCritiques()
	if err != nil || n != 1 {
		t.Fatalf("expected 1 critique row, got %d err=%v", n, err)
	}
}

func TestCriticAgent_NoRegenerationOnHighScore(t *testing.T) {
	bus := eventbus.New()
	collector := &eventCollector{}
	bus.Subscribe(eventbus.TeachingResponse, collector.handler)

	llmService := llm.NewLlmServiceWithConfig(&fakeProvider{}, 1, 0, 5, time.Minute)
	agent := NewCriticAgent(bus, llmService)
	agent.Start()

	// 发布一个高质量回复(长文本 + 提问 + 鼓励 + 引导) -- 启发式评分应 > 3.0
	bus.Publish(eventbus.Event{
		Type: eventbus.TeachingResponse, Source: "TutorAgent",
		LearnerID: "learner1",
		Data: map[string]interface{}{
			"knowledge_id": "algebra",
			"response": "很好！你做得不错！让我们一起来思考这个问题。" +
				"试着想一想,这个知识点和之前学过的哪些内容有关?" +
				"如果卡住了,可以想想:这个问题的关键点是什么?试着说说你的理解。" +
				"加油,你一定能想出来的!",
			"teaching_style": "socratic",
			"difficulty_level": "developing",
			"mastery":        0.6,
		},
	})

	time.Sleep(300 * time.Millisecond)

	// 验证没有发布 regenerated=true 的 TeachingResponse
	for _, e := range collector.getEvents() {
		if regen, ok := e.Data["regenerated"].(bool); ok && regen {
			t.Error("high-quality response should NOT trigger regeneration")
		}
	}
}

// ─── DebateAgent 测试 ───

func TestDebateAgent_SkipsWhenDebateModeFalse(t *testing.T) {
	bus := eventbus.New()
	collector := &eventCollector{}
	bus.Subscribe(eventbus.DebateConsensus, collector.handler)

	llmService := llm.NewLlmServiceWithConfig(&fakeProvider{}, 1, 0, 5, time.Minute)
	agent := NewDebateAgent(bus, llmService)
	agent.Start()

	// 发布 debate_mode=false 的事件
	bus.Publish(eventbus.Event{
		Type: eventbus.StudentQuestion, Source: "Student",
		LearnerID: "learner1",
		Data: map[string]interface{}{
			"question":     "什么是方程",
			"debate_mode":  false,
			"knowledge_id": "algebra",
		},
	})

	time.Sleep(100 * time.Millisecond)

	if collector.countByType(eventbus.DebateConsensus) != 0 {
		t.Errorf("DebateAgent should skip when debate_mode=false, got %d events",
			collector.countByType(eventbus.DebateConsensus))
	}
}

func TestDebateAgent_SkipsEmptyQuestion(t *testing.T) {
	bus := eventbus.New()
	collector := &eventCollector{}
	bus.Subscribe(eventbus.DebateConsensus, collector.handler)

	llmService := llm.NewLlmServiceWithConfig(&fakeProvider{}, 1, 0, 5, time.Minute)
	agent := NewDebateAgent(bus, llmService)
	agent.Start()

	// 发布空问题
	bus.Publish(eventbus.Event{
		Type: eventbus.StudentQuestion, Source: "Student",
		LearnerID: "learner1",
		Data: map[string]interface{}{
			"question":    "",
			"debate_mode": true,
		},
	})

	time.Sleep(100 * time.Millisecond)

	if collector.countByType(eventbus.DebateConsensus) != 0 {
		t.Errorf("DebateAgent should skip empty questions, got %d events",
			collector.countByType(eventbus.DebateConsensus))
	}
}

func TestDebateAgent_GeneratesConsensus(t *testing.T) {
	bus := eventbus.New()
	collector := &eventCollector{}
	bus.Subscribe(eventbus.DebateConsensus, collector.handler)

	llmService := llm.NewLlmServiceWithConfig(&fakeProvider{}, 1, 0, 5, time.Minute)
	agent := NewDebateAgent(bus, llmService)
	agent.Start()

	// 发布 debate_mode=true 的问题
	bus.Publish(eventbus.Event{
		Type: eventbus.StudentQuestion, Source: "Student",
		LearnerID: "learner1",
		Data: map[string]interface{}{
			"question":     "什么是勾股定理",
			"debate_mode":  true,
			"knowledge_id": "pythagorean",
			"level":        "beginner",
			"mastery":      0.3,
		},
	})

	time.Sleep(200 * time.Millisecond)

	// 验证发布了 DebateConsensus 事件
	debateEvents := collector.countByType(eventbus.DebateConsensus)
	if debateEvents != 1 {
		t.Errorf("expected 1 DebateConsensus event, got %d", debateEvents)
	}

	events := collector.getEvents()
	if len(events) != 1 {
		t.Fatalf("expected 1 event, got %d", len(events))
	}

	// 验证事件内容
	e := events[0]
	if e.Data["knowledge_id"] != "pythagorean" {
		t.Errorf("expected knowledge_id=pythagorean, got %v", e.Data["knowledge_id"])
	}
	if e.Data["teaching_style"] != "debate_synthesis" {
		t.Errorf("expected teaching_style=debate_synthesis, got %v", e.Data["teaching_style"])
	}
	if _, ok := e.Data["response"]; !ok {
		t.Error("expected 'response' field in DebateConsensus event")
	}
	if _, ok := e.Data["socratic_final"]; !ok {
		t.Error("expected 'socratic_final' field")
	}
	if _, ok := e.Data["direct_final"]; !ok {
		t.Error("expected 'direct_final' field")
	}
}

func TestDebateAgent_UsesHeuristicFallback(t *testing.T) {
	bus := eventbus.New()
	collector := &eventCollector{}
	bus.Subscribe(eventbus.DebateConsensus, collector.handler)

	// 使用 fakeProvider(始终失败) -> 降级到启发式
	llmService := llm.NewLlmServiceWithConfig(&fakeProvider{}, 1, 0, 5, time.Minute)
	agent := NewDebateAgent(bus, llmService)
	agent.Start()

	bus.Publish(eventbus.Event{
		Type: eventbus.StudentQuestion, Source: "Student",
		LearnerID: "learner1",
		Data: map[string]interface{}{
			"question":     "如何理解函数",
			"debate_mode":  true,
			"knowledge_id": "functions",
		},
	})

	time.Sleep(200 * time.Millisecond)

	events := collector.getEvents()
	if len(events) != 1 {
		t.Fatalf("expected 1 event, got %d", len(events))
	}

	// 验证启发式降级: metadata.llm_used == false
	metadata, ok := events[0].Data["debate_metadata"].(map[string]interface{})
	if !ok {
		t.Fatal("expected debate_metadata in event")
	}
	if llmUsed, ok := metadata["llm_used"].(bool); !ok || llmUsed {
		t.Error("expected llm_used=false for heuristic fallback")
	}
	if orchestrator, ok := metadata["orchestrator"].(string); !ok || orchestrator != "heuristic_stub" {
		t.Errorf("expected orchestrator=heuristic_stub, got %v", orchestrator)
	}
}

func TestDebateAgent_DefaultsKnowledgeIDAndLevel(t *testing.T) {
	bus := eventbus.New()
	collector := &eventCollector{}
	bus.Subscribe(eventbus.DebateConsensus, collector.handler)

	llmService := llm.NewLlmServiceWithConfig(&fakeProvider{}, 1, 0, 5, time.Minute)
	agent := NewDebateAgent(bus, llmService)
	agent.Start()

	// 不提供 knowledge_id 和 level
	bus.Publish(eventbus.Event{
		Type: eventbus.StudentQuestion, Source: "Student",
		LearnerID: "learner1",
		Data: map[string]interface{}{
			"question":    "测试问题",
			"debate_mode": true,
		},
	})

	time.Sleep(200 * time.Millisecond)

	events := collector.getEvents()
	if len(events) != 1 {
		t.Fatalf("expected 1 event, got %d", len(events))
	}

	// 验证默认值
	if events[0].Data["knowledge_id"] != "general" {
		t.Errorf("expected default knowledge_id=general, got %v", events[0].Data["knowledge_id"])
	}
}
