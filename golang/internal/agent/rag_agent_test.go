package agent

import (
	"testing"
	"time"

	"multi-agent-education/golang/internal/eventbus"
	"multi-agent-education/golang/internal/rag"
)

func TestRAGAgent_HandleStudentQuestion(t *testing.T) {
	bus := eventbus.New()
	ragService := rag.NewRAGService(rag.NewMockEmbeddingProvider(), rag.NewInMemoryVectorStore())

	// 摄取测试文档
	ragService.IngestDocument("doc-001", "勾股定理是指直角三角形两直角边的平方和等于斜边的平方。")

	// 先注册收集器，再启动 Agent，避免竞态
	var published []eventbus.Event
	bus.Subscribe(eventbus.RAGDocumentIngested, func(e eventbus.Event) {
		published = append(published, e)
	})

	agent := NewRAGAgent(bus, ragService)
	go agent.Start()

	// 等待 Agent 完成订阅注册
	time.Sleep(100 * time.Millisecond)

	// 发布学生提问
	bus.Publish(eventbus.Event{
		Type:      eventbus.StudentQuestion,
		Source:    "test",
		LearnerID: "learner-001",
		Data:      map[string]interface{}{"question": "什么是勾股定理"},
	})

	// 等待处理
	time.Sleep(500 * time.Millisecond)

	if len(published) == 0 {
		t.Error("RAGAgent should publish RAGDocumentIngested event")
	}
}

func TestRAGAgent_SkipEmptyQuestion(t *testing.T) {
	bus := eventbus.New()
	ragService := rag.NewRAGService(rag.NewMockEmbeddingProvider(), rag.NewInMemoryVectorStore())

	agent := NewRAGAgent(bus, ragService)
	go agent.Start()

	var published []eventbus.Event
	bus.Subscribe(eventbus.RAGDocumentIngested, func(e eventbus.Event) {
		published = append(published, e)
	})

	// 发布空问题
	bus.Publish(eventbus.Event{
		Type:   eventbus.StudentQuestion,
		Source: "test",
		Data:   map[string]interface{}{"question": ""},
	})

	time.Sleep(200 * time.Millisecond)

	if len(published) != 0 {
		t.Error("RAGAgent should skip empty questions")
	}
}
