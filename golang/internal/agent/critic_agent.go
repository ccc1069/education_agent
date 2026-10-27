package agent

import (
	"log"
	"math"
	"sync"
	"time"

	"multi-agent-education/golang/internal/eventbus"
	"multi-agent-education/golang/internal/llm"
	"multi-agent-education/golang/internal/persist"
)

// CriticAgent Critic Agent -- LLM-as-judge 教学回复评估 + 自反思再生成(P2#16a)。
//
// 对齐 Python critic_agent.py:
// 1. 订阅 TEACHING_RESPONSE 事件
// 2. 用 CriticService 评估回复质量(4 维度 + overall 1-5 分)
// 3. 低分(overall <= 3)时触发自反思: 把 critique 作为反馈让 Tutor 重新生成
// 4. 发布 TEACHING_CRITICIZED 事件携带评估结果；可选落库 critiques
//
// 设计原则:
// - 失败降级: LLM 不可用时跳过评估不阻塞主流程
// - 单次重生成: 最多重生成一次,避免循环(regenerated=True 的事件不再评估)
// - 不修改 TutorAgent: 通过事件订阅解耦
type CriticAgent struct {
	bus           *eventbus.EventBus
	llm           *llm.LlmService
	criticService *llm.CriticService
	persistDB     *persist.DB
	// 防循环: 已触发重生成的 teaching event ID 集合
	regenerating map[string]time.Time
	mu           sync.Mutex
}

// NewCriticAgent 创建 CriticAgent
func NewCriticAgent(bus *eventbus.EventBus, llmService *llm.LlmService) *CriticAgent {
	return &CriticAgent{
		bus:           bus,
		llm:           llmService,
		criticService: llm.NewCriticService(llmService),
		regenerating:  make(map[string]time.Time),
	}
}

// SetPersist 启用 critiques 表落盘（对齐 Java CritiqueRepository）。
func (a *CriticAgent) SetPersist(db *persist.DB) {
	a.persistDB = db
}

// Start 启动 CriticAgent 事件监听
func (a *CriticAgent) Start() {
	a.bus.Subscribe(eventbus.TeachingResponse, a.handleTeachingResponse)
}

// handleTeachingResponse 处理教学回复事件
func (a *CriticAgent) handleTeachingResponse(event eventbus.Event) {
	// 跳过自己发布的重生成事件,避免循环
	if regenerated, ok := event.Data["regenerated"].(bool); ok && regenerated {
		return
	}
	// 跳过 hint 转发(无 LLM 评估意义)
	if style, ok := event.Data["teaching_style"].(string); ok && style == "hint" {
		return
	}

	knowledgeID, _ := event.Data["knowledge_id"].(string)
	responseText, _ := event.Data["response"].(string)
	level, _ := event.Data["difficulty_level"].(string)
	if level == "" {
		level, _ = event.Data["level"].(string)
	}
	if level == "" {
		level = "beginner"
	}
	mastery, _ := event.Data["mastery"].(float64)
	question, _ := event.Data["question"].(string)
	isCorrect, ok := eventbus.DataBool(event.Data, "is_correct")
	var isCorrectPtr *bool
	if ok {
		isCorrectPtr = &isCorrect
	}

	// 1. 评估
	critique := a.criticService.Evaluate(knowledgeID, level, mastery, isCorrectPtr, responseText, question)
	if critique == nil {
		log.Printf("[Critic] skipped (LLM unavailable) event=%s", event.ID)
		return
	}

	// 2. 落库（失败不阻塞事件发布）
	a.saveCritique(event, knowledgeID, responseText, critique)

	// 3. 发布 TEACHING_CRITICIZED
	a.bus.Publish(eventbus.Event{
		Type: eventbus.TeachingCriticized, Source: "CriticAgent",
		LearnerID: event.LearnerID,
		Data: map[string]interface{}{
			"knowledge_id":       knowledgeID,
			"teaching_event_id":  event.ID,
			"overall":            critique.Overall,
			"scores":             critique.Scores,
			"critique":           critique.Critique,
			"needs_regeneration": critique.NeedsRegeneration,
			"critic_model":       critique.Model,
			"critic_tokens":      critique.Tokens,
		},
	})

	log.Printf("[Critic] evaluated: overall=%.0f needs_regen=%v learner=%s",
		critique.Overall, critique.NeedsRegeneration, event.LearnerID)

	// 4. 低分(overall <= 3) -> 触发自反思再生成
	if critique.NeedsRegeneration && a.markRegenerating(event.ID) {
		a.regenerateAndPublish(event, knowledgeID, level, mastery, isCorrectPtr, question, responseText, critique)
	}
}

func (a *CriticAgent) saveCritique(event eventbus.Event, knowledgeID, responseText string, critique *llm.CritiqueResult) {
	if a.persistDB == nil {
		return
	}
	_, err := a.persistDB.InsertCritique(persist.CritiqueRow{
		LearnerID:         event.LearnerID,
		KnowledgeID:       knowledgeID,
		TeachingEventID:   event.ID,
		Overall:           int(math.Round(critique.Overall)),
		Scores:            critique.Scores,
		Critique:          critique.Critique,
		NeedsRegeneration: critique.NeedsRegeneration,
		OriginalResponse:  responseText,
		CriticModel:       critique.Model,
		CriticTokens:      critique.Tokens,
	})
	if err != nil {
		log.Printf("[Critic] persist critique: %v", err)
	}
}

// regenerateAndPublish 执行自反思再生成并发布新回复
func (a *CriticAgent) regenerateAndPublish(event eventbus.Event, knowledgeID, level string,
	mastery float64, isCorrect *bool, question, originalResponse string, critique *llm.CritiqueResult) {

	defer a.unmarkRegenerating(event.ID)

	regen := a.criticService.Regenerate(knowledgeID, level, mastery, isCorrect, originalResponse, critique.Critique, question)

	if a.persistDB != nil {
		if err := a.persistDB.MarkCritiqueRegenerated(event.ID, regen.Text); err != nil {
			log.Printf("[Critic] mark regenerated: %v", err)
		}
	}

	a.bus.Publish(eventbus.Event{
		Type: eventbus.TeachingResponse, Source: "CriticAgent",
		LearnerID: event.LearnerID,
		Data: map[string]interface{}{
			"knowledge_id":        knowledgeID,
			"response":            regen.Text,
			"teaching_style":      "socratic",
			"difficulty_level":    level,
			"regenerated":         true,
			"critic_overall":      critique.Overall,
			"critic_critique":     critique.Critique,
			"llm_used":            regen.Metadata["llm_used"],
			"regenerated_success": regen.Metadata["regenerated"],
		},
	})

	log.Printf("[Critic] regenerated response (overall=%.0f learner=%s)",
		critique.Overall, event.LearnerID)
}

// markRegenerating 标记 event ID 正在重生成,返回是否成功(防重复)
func (a *CriticAgent) markRegenerating(eventID string) bool {
	a.mu.Lock()
	defer a.mu.Unlock()
	if _, exists := a.regenerating[eventID]; exists {
		return false
	}
	a.regenerating[eventID] = time.Now()
	return true
}

// unmarkRegenerating 取消标记
func (a *CriticAgent) unmarkRegenerating(eventID string) {
	a.mu.Lock()
	defer a.mu.Unlock()
	delete(a.regenerating, eventID)
}
