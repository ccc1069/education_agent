package agent

import (
	"log"

	"multi-agent-education/golang/internal/eventbus"
	"multi-agent-education/golang/internal/llm"
)

// DebateAgent Multi-Agent Debate Agent -- 对齐 Java DebateAgent
//
// 行为:
// 1. 订阅 StudentQuestion 事件
// 2. 仅当 data.debate_mode == true 时触发
// 3. 调 DebateService.RunDebate() 执行 N 轮辩论(socratic vs direct)+ Synthesizer 综合
// 4. 发布 DebateConsensus 事件携带共识结果
//
// 设计原则:
// - 失败降级: LLM 不可用时降级到启发式综合,不阻塞主流程
// - 不修改 TutorAgent: 通过事件订阅解耦
// - 空问题跳过: 无问题文本时不触发辩论
type DebateAgent struct {
	bus           *eventbus.EventBus
	llm           *llm.LlmService
	debateService *llm.DebateService
}

// NewDebateAgent 创建 DebateAgent
func NewDebateAgent(bus *eventbus.EventBus, llmService *llm.LlmService) *DebateAgent {
	return &DebateAgent{
		bus:           bus,
		llm:           llmService,
		debateService: llm.NewDebateService(llmService, llm.GetDebateRounds()),
	}
}

// Start 启动 DebateAgent 事件监听
func (a *DebateAgent) Start() {
	a.bus.Subscribe(eventbus.StudentQuestion, a.handleStudentQuestion)
}

// handleStudentQuestion 处理学生提问事件
func (a *DebateAgent) handleStudentQuestion(event eventbus.Event) {
	// 仅当 debate_mode=true 时触发
	if debateMode, ok := event.Data["debate_mode"].(bool); !ok || !debateMode {
		return
	}

	question, _ := event.Data["question"].(string)
	knowledgeID, _ := event.Data["knowledge_id"].(string)
	level, _ := event.Data["level"].(string)
	mastery, _ := event.Data["mastery"].(float64)

	// 跳过空问题
	if question == "" {
		log.Printf("[Debate] skipped: empty question learner=%s", event.LearnerID)
		return
	}
	if knowledgeID == "" {
		knowledgeID = "general"
	}
	if level == "" {
		level = "beginner"
	}

	// 执行辩论
	result := a.debateService.RunDebate(knowledgeID, level, mastery, question)

	// 发布 DebateConsensus 事件
	a.bus.Publish(eventbus.Event{
		Type: eventbus.DebateConsensus, Source: "DebateAgent",
		LearnerID: event.LearnerID,
		Data: map[string]interface{}{
			"knowledge_id":      knowledgeID,
			"question":          question,
			"response":          result.Consensus,
			"teaching_style":    "debate_synthesis",
			"socratic_final":    result.SocraticFinal,
			"direct_final":      result.DirectFinal,
			"rounds_completed":  result.RoundsCompleted,
			"debate_metadata":   result.Metadata,
		},
	})

	log.Printf("[Debate] consensus generated: rounds=%d llm_used=%v learner=%s",
		result.RoundsCompleted, result.Metadata["llm_used"], event.LearnerID)
}
