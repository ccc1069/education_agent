package agent

import (
	"fmt"
	"log"

	"multi-agent-education/golang/internal/eventbus"
	"multi-agent-education/golang/internal/rag"
)

// RAGAgent RAG 检索增强 Agent
//
// 面试要点:
// - 订阅 StudentQuestion 事件
// - 使用 RAG 服务进行语义检索
// - 将检索结果附加到 TeachingResponse
//
// 行为:
// 1. 收到学生提问
// 2. 调用 ragService.Search() 检索相关文档
// 3. 发布 TeachingResponse 事件 (含检索上下文)
type RAGAgent struct {
	bus        *eventbus.EventBus
	ragService *rag.RAGService
}

// NewRAGAgent 创建 RAG Agent
func NewRAGAgent(bus *eventbus.EventBus, ragService *rag.RAGService) *RAGAgent {
	return &RAGAgent{
		bus:        bus,
		ragService: ragService,
	}
}

// Start 启动 RAG Agent 事件监听
func (a *RAGAgent) Start() {
	a.bus.Subscribe(eventbus.StudentQuestion, a.handleStudentQuestion)
	log.Println("[RAGAgent] 已启动,订阅 StudentQuestion 事件")
}

// handleStudentQuestion 处理学生提问
func (a *RAGAgent) handleStudentQuestion(event eventbus.Event) {
	question, ok := event.Data["question"].(string)
	if !ok || question == "" {
		return
	}

	// 语义检索
	results, err := a.ragService.Search(question, 3)
	if err != nil {
		log.Printf("[RAGAgent] 检索失败: %v", err)
		return
	}

	// 发布 RAG 检索结果事件
	a.bus.Publish(eventbus.Event{
		Type:      eventbus.RAGDocumentIngested,
		Source:    "rag-agent",
		LearnerID: event.LearnerID,
		Data: map[string]interface{}{
			"query":   question,
			"results": results,
			"context": formatRAGContext(results),
		},
		CorrelationID: event.CorrelationID,
	})
}

// formatRAGContext 格式化 RAG 检索结果为上下文
func formatRAGContext(results []rag.SearchResult) string {
	if len(results) == 0 {
		return ""
	}
	var context string
	for i, r := range results {
		if text, ok := r.Metadata["text"].(string); ok {
			context += fmt.Sprintf("[%d] %s\n", i+1, text)
		}
	}
	return context
}
