package eventbus

import (
	"crypto/rand"
	"fmt"
	"log"
	"sync"
	"time"
)

// EventType 事件类型枚举
type EventType string

const (
	StudentSubmission  EventType = "student.submission"
	StudentQuestion    EventType = "student.question"
	StudentMessage     EventType = "student.message"
	AssessmentComplete EventType = "assessment.complete"
	MasteryUpdated     EventType = "assessment.mastery_updated"
	WeaknessDetected   EventType = "assessment.weakness_detected"
	TeachingResponse   EventType = "tutor.teaching_response"
	HintNeeded         EventType = "tutor.hint_needed"
	DifficultyAdjusted EventType = "tutor.difficulty_adjusted"
	PathUpdated        EventType = "curriculum.path_updated"
	ReviewScheduled    EventType = "curriculum.review_scheduled"
	NextTopic          EventType = "curriculum.next_topic"
	HintResponse       EventType = "hint.response"
	EngagementAlert    EventType = "engagement.alert"
	Encouragement      EventType = "engagement.encouragement"
	PaceAdjustment     EventType = "engagement.pace_adjustment"
	TeachingCriticized EventType = "tutor.teaching_criticized"
	DebateConsensus    EventType = "tutor.debate_consensus"
	// Phase 1: 企业基础设施
	AuditLogged    EventType = "audit.logged"
	ConsentUpdated EventType = "privacy.consent_updated"
	UserRegistered EventType = "auth.user_registered"
	// Phase 2: 核心教学
	RAGDocumentIngested EventType = "rag.document_ingested"
	QuestionGenerated   EventType = "question.generated"
	QuestionAnswered    EventType = "question.answered"
	AssignmentCreated   EventType = "assignment.created"
	NotificationSent    EventType = "notification.sent"
	ClassCreated        EventType = "class.created"
	TaskScheduled       EventType = "scheduler.task_scheduled"
	// Phase 3: 可观测性
	VisionAnalyzed EventType = "vision.analyzed"
)

// Event 事件数据结构
type Event struct {
	ID            string                 `json:"id"`
	Type          EventType              `json:"type"`
	Source        string                 `json:"source"`
	LearnerID     string                 `json:"learner_id"`
	Timestamp     time.Time              `json:"timestamp"`
	Data          map[string]interface{} `json:"data"`
	CorrelationID string                 `json:"correlation_id"`
}

// Handler 事件处理函数
type Handler func(Event)

// EventBus 事件总线 -- 同步分发，对齐 Python await asyncio.gather。
type EventBus struct {
	subscribers map[EventType][]Handler
	history     []Event
	mu          sync.RWMutex
	persist     func(Event)
}

// New 创建 EventBus 实例
func New() *EventBus {
	return &EventBus{
		subscribers: make(map[EventType][]Handler),
		history:     make([]Event, 0),
	}
}

// SetPersist 设置事件落库回调（对齐 Python EventPersistenceService）。
func (b *EventBus) SetPersist(fn func(Event)) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.persist = fn
}

// Subscribe 订阅事件
func (b *EventBus) Subscribe(eventType EventType, handler Handler) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.subscribers[eventType] = append(b.subscribers[eventType], handler)
}

// DataBool 安全读取 bool 字段；缺字段或类型不对时 ok=false（不会默认为 false 答错）。
func DataBool(data map[string]interface{}, key string) (bool, bool) {
	if data == nil {
		return false, false
	}
	v, exists := data[key]
	if !exists || v == nil {
		return false, false
	}
	b, ok := v.(bool)
	return b, ok
}

// Publish 发布事件：写入历史后并发通知订阅者，并等待全部完成。
func (b *EventBus) Publish(event Event) {
	if event.ID == "" {
		idBytes := make([]byte, 8)
		_, _ = rand.Read(idBytes)
		event.ID = fmt.Sprintf("%x", idBytes)
	}
	if event.CorrelationID == "" {
		corrBytes := make([]byte, 8)
		_, _ = rand.Read(corrBytes)
		event.CorrelationID = fmt.Sprintf("%x", corrBytes)
	}
	event.Timestamp = time.Now()

	b.mu.Lock()
	b.history = append(b.history, event)
	handlers := append([]Handler(nil), b.subscribers[event.Type]...)
	persistFn := b.persist
	b.mu.Unlock()

	if persistFn != nil {
		persistFn(event)
	}

	log.Printf("[EventBus] %s -> %s (learner=%s)", event.Source, event.Type, event.LearnerID)

	if len(handlers) == 0 {
		return
	}

	var wg sync.WaitGroup
	for _, h := range handlers {
		wg.Add(1)
		go func(handler Handler) {
			defer wg.Done()
			defer func() {
				if r := recover(); r != nil {
					log.Printf("[EventBus] Handler panic: %v", r)
				}
			}()
			handler(event)
		}(h)
	}
	wg.Wait()
}

// GetHistory 获取事件历史（last-N）
func (b *EventBus) GetHistory(learnerID string, limit int) []Event {
	b.mu.RLock()
	defer b.mu.RUnlock()

	var filtered []Event
	for _, e := range b.history {
		if learnerID == "" || e.LearnerID == learnerID {
			filtered = append(filtered, e)
		}
	}
	if limit > 0 && len(filtered) > limit {
		filtered = filtered[len(filtered)-limit:]
	}
	return filtered
}
