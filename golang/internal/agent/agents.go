package agent

import (
	"fmt"
	"log"
	"math"
	"sync"
	"time"

	"multi-agent-education/golang/internal/eventbus"
	"multi-agent-education/golang/internal/model"
)

// ─── Assessment Agent ───

type AssessmentAgent struct {
	bus     *eventbus.EventBus
	Models  map[string]*model.LearnerModel
	mu      sync.RWMutex
	persist learnerPersist
}

// learnerPersist SQLite MVP 适配面（由 persist.DB 实现）。
type learnerPersist interface {
	Hydrate(m *model.LearnerModel) error
	Save(m *model.LearnerModel) error
}

func NewAssessmentAgent(bus *eventbus.EventBus) *AssessmentAgent {
	return &AssessmentAgent{bus: bus, Models: make(map[string]*model.LearnerModel)}
}

// SetPersist 启用 knowledge_states 落盘。
func (a *AssessmentAgent) SetPersist(p learnerPersist) {
	a.persist = p
}

func (a *AssessmentAgent) Start() {
	a.bus.Subscribe(eventbus.StudentSubmission, a.handleSubmission)
}

func (a *AssessmentAgent) GetModel(learnerID string) *model.LearnerModel {
	a.mu.Lock()
	defer a.mu.Unlock()
	m, ok := a.Models[learnerID]
	if !ok {
		m = model.NewLearnerModel(learnerID)
		a.Models[learnerID] = m
		if a.persist != nil {
			if err := a.persist.Hydrate(m); err != nil {
				log.Printf("[Assessment] hydrate learner=%s err=%v", learnerID, err)
			}
		}
	}
	return m
}

// LearnerProgress 学习进度
type LearnerProgress struct {
	LearnerID string                    `json:"learner_id"`
	States    []model.KnowledgeState    `json:"states"`
	WeakPoints []model.KnowledgeState   `json:"weak_points"`
}

// GetProgress 获取学习者进度
func (a *AssessmentAgent) GetProgress(learnerID string) *LearnerProgress {
	m := a.GetModel(learnerID)
	weakPtrs := m.GetWeakPoints(0.3)
	weak := make([]model.KnowledgeState, 0, len(weakPtrs))
	for _, wp := range weakPtrs {
		weak = append(weak, *wp)
	}
	return &LearnerProgress{
		LearnerID:  learnerID,
		States:     m.GetAllStates(),
		WeakPoints: weak,
	}
}

func (a *AssessmentAgent) handleSubmission(event eventbus.Event) {
	knowledgeID, _ := event.Data["knowledge_id"].(string)
	isCorrect, ok := eventbus.DataBool(event.Data, "is_correct")
	if !ok {
		isCorrect = false
	}

	m := a.GetModel(event.LearnerID)
	state := m.UpdateMastery(knowledgeID, isCorrect)

	log.Printf("[Assessment] learner=%s, kp=%s, correct=%v, mastery=%.3f (%s)",
		event.LearnerID, knowledgeID, isCorrect, state.Mastery, state.Level())

	if a.persist != nil {
		if err := a.persist.Save(m); err != nil {
			log.Printf("[Assessment] save learner=%s err=%v", event.LearnerID, err)
		}
	}

	a.bus.Publish(eventbus.Event{
		Type: eventbus.MasteryUpdated, Source: "AssessmentAgent",
		LearnerID: event.LearnerID,
		Data: map[string]interface{}{
			"knowledge_id": knowledgeID, "mastery": state.Mastery,
			"level": state.Level(), "is_correct": isCorrect, "attempts": state.Attempts,
		},
	})

	if state.Mastery < 0.3 && state.Attempts >= 3 {
		a.bus.Publish(eventbus.Event{
			Type: eventbus.WeaknessDetected, Source: "AssessmentAgent",
			LearnerID: event.LearnerID,
			Data: map[string]interface{}{"knowledge_id": knowledgeID, "mastery": state.Mastery},
		})
	}

	a.bus.Publish(eventbus.Event{
		Type: eventbus.AssessmentComplete, Source: "AssessmentAgent",
		LearnerID: event.LearnerID,
		Data: map[string]interface{}{
			"knowledge_id": knowledgeID, "mastery": state.Mastery,
			"level": state.Level(), "is_correct": isCorrect,
		},
	})
}

// ─── Tutor Agent ───

type TutorAgent struct {
	bus      *eventbus.EventBus
	attempts map[string]int
	mu       sync.Mutex
}

func NewTutorAgent(bus *eventbus.EventBus) *TutorAgent {
	return &TutorAgent{bus: bus, attempts: make(map[string]int)}
}

func (t *TutorAgent) Start() {
	t.bus.Subscribe(eventbus.AssessmentComplete, t.handleAssessment)
	t.bus.Subscribe(eventbus.EngagementAlert, t.handleEngagement)
	t.bus.Subscribe(eventbus.StudentMessage, t.handleStudentMessage)
	t.bus.Subscribe(eventbus.HintResponse, t.handleHintResponse)
}

func (t *TutorAgent) handleStudentMessage(event eventbus.Event) {
	knowledgeID, _ := event.Data["knowledge_id"].(string)
	question, _ := event.Data["question"].(string)
	if knowledgeID == "" {
		knowledgeID = "general"
	}
	response := fmt.Sprintf("好的，关于「%s」，你的问题是：%s\n在我回答之前，让我先问你：\n你对这个知识点已经了解了哪些内容？试着说说你的理解。",
		knowledgeID, question)

	t.bus.Publish(eventbus.Event{
		Type: eventbus.TeachingResponse, Source: "TutorAgent",
		LearnerID: event.LearnerID,
		Data: map[string]interface{}{
			"knowledge_id": knowledgeID, "response": response,
			"teaching_style": "socratic", "difficulty_level": "adaptive",
		},
	})
}

func (t *TutorAgent) handleHintResponse(event eventbus.Event) {
	t.bus.Publish(eventbus.Event{
		Type: eventbus.TeachingResponse, Source: "TutorAgent",
		LearnerID: event.LearnerID,
		Data: map[string]interface{}{
			"knowledge_id": event.Data["knowledge_id"],
			"response":     event.Data["hint_text"],
			"teaching_style": "hint",
			"hint_level":   event.Data["hint_level"],
		},
	})
}

func (t *TutorAgent) handleAssessment(event eventbus.Event) {
	knowledgeID, _ := event.Data["knowledge_id"].(string)
	level, _ := event.Data["level"].(string)
	isCorrect, hasCorrect := eventbus.DataBool(event.Data, "is_correct")
	mastery, _ := event.Data["mastery"].(float64)

	if hasCorrect && !isCorrect {
		key := event.LearnerID + ":" + knowledgeID
		t.mu.Lock()
		t.attempts[key]++
		attempts := t.attempts[key]
		t.mu.Unlock()
		if attempts >= 2 {
			t.bus.Publish(eventbus.Event{
				Type: eventbus.HintNeeded, Source: "TutorAgent",
				LearnerID: event.LearnerID,
				Data: map[string]interface{}{
					"knowledge_id": knowledgeID, "attempts": attempts,
					"mastery": mastery, "level": level,
				},
			})
			return
		}
	}

	toneCorrect := true
	if hasCorrect {
		toneCorrect = isCorrect
	}
	response := generateSocraticResponse(knowledgeID, level, mastery, toneCorrect)

	t.bus.Publish(eventbus.Event{
		Type: eventbus.TeachingResponse, Source: "TutorAgent",
		LearnerID: event.LearnerID,
		Data: map[string]interface{}{
			"knowledge_id": knowledgeID, "response": response,
			"teaching_style": "socratic", "difficulty_level": level,
			"prompt_template_used": level,
		},
	})
}

func generateSocraticResponse(knowledgeID, level string, mastery float64, isCorrect bool) string {
	prompts := map[string]string{
		"beginner":   "请用最简单的语言和例子帮助学生理解概念，先问学生对相关基础概念是否了解",
		"developing": "通过提问引导学生思考，引导发现问题的关键步骤",
		"proficient": "提出更深层的思考问题，引导发现知识点之间的联系",
		"mastered":   "引导学生总结归纳方法论，布置跨知识点的挑战题",
	}
	prompt := prompts[level]
	if prompt == "" {
		prompt = prompts["beginner"]
	}

	if isCorrect {
		return fmt.Sprintf("很好！你在「%s」上的表现不错。当前掌握度：%.0f%%。\n让我问你一个更深入的问题：你能用自己的话解释一下这个概念吗？\n[教学策略: %s]",
			knowledgeID, mastery*100, prompt)
	}
	return fmt.Sprintf("没关系，让我们一起来分析「%s」。\n先不看答案，我想问你：\n1. 你觉得这道题考查的是什么知识点？\n2. 你做题的时候卡在了哪一步？\n[教学策略: %s]",
		knowledgeID, prompt)
}

func (t *TutorAgent) handleEngagement(event eventbus.Event) {
	alertType, _ := event.Data["alert_type"].(string)
	data := map[string]interface{}{}
	if alertType == "frustration" {
		data["action"] = "decrease"
		data["message"] = "让我们换一个角度，从更简单的地方开始。"
	} else if alertType == "boredom" {
		data["action"] = "increase"
		data["message"] = "让我给你一个更有挑战性的问题！"
	}
	if len(data) > 0 {
		t.bus.Publish(eventbus.Event{
			Type: eventbus.DifficultyAdjusted, Source: "TutorAgent",
			LearnerID: event.LearnerID, Data: data,
		})
	}
}

// ─── Curriculum Agent ───

type CurriculumAgent struct {
	bus            *eventbus.EventBus
	reviewItems    map[string]map[string]*model.ReviewItem
	knowledgeGraph *model.KnowledgeGraph
	mu             sync.Mutex
}

func NewCurriculumAgent(bus *eventbus.EventBus) *CurriculumAgent {
	return &CurriculumAgent{
		bus:            bus,
		reviewItems:    make(map[string]map[string]*model.ReviewItem),
		knowledgeGraph: model.BuildSampleMathGraph(),
	}
}

func (c *CurriculumAgent) Start() {
	c.bus.Subscribe(eventbus.MasteryUpdated, c.handleMasteryUpdate)
	c.bus.Subscribe(eventbus.WeaknessDetected, c.handleWeakness)
	c.bus.Subscribe(eventbus.PaceAdjustment, c.handlePaceAdjustment)
}

func (c *CurriculumAgent) handleMasteryUpdate(event eventbus.Event) {
	knowledgeID, _ := event.Data["knowledge_id"].(string)
	mastery, _ := event.Data["mastery"].(float64)

	c.mu.Lock()
	if _, ok := c.reviewItems[event.LearnerID]; !ok {
		c.reviewItems[event.LearnerID] = make(map[string]*model.ReviewItem)
	}
	item, ok := c.reviewItems[event.LearnerID][knowledgeID]
	if !ok {
		item = model.NewReviewItem(knowledgeID)
		c.reviewItems[event.LearnerID][knowledgeID] = item
	}
	c.mu.Unlock()

	quality := masteryToQuality(mastery)
	model.SM2Review(item, quality)

	log.Printf("[Curriculum] learner=%s, kp=%s, EF=%.2f, interval=%.1fd",
		event.LearnerID, knowledgeID, item.EasinessFactor, item.IntervalDays)

	// 发送复习计划
	c.sendReviewSchedule(event.LearnerID)

	// 推荐下一知识点
	if mastery >= 0.6 {
		c.checkAndRecommendNext(event.LearnerID)
	}
}

func (c *CurriculumAgent) getMasteredIDs(learnerID string) map[string]bool {
	mastered := make(map[string]bool)
	c.mu.Lock()
	defer c.mu.Unlock()
	if items, ok := c.reviewItems[learnerID]; ok {
		for id, item := range items {
			if item.EasinessFactor >= 2.0 {
				mastered[id] = true
			}
		}
	}
	return mastered
}

func (c *CurriculumAgent) checkAndRecommendNext(learnerID string) {
	masteredIDs := c.getMasteredIDs(learnerID)
	ready := c.knowledgeGraph.GetReadyNodes(masteredIDs)
	if len(ready) > 0 {
		nextTopic := ready[0]
		node := c.knowledgeGraph.GetNode(nextTopic)
		name := nextTopic
		difficulty := 0.5
		if node != nil {
			name = node.Name
			difficulty = node.Difficulty
		}
		alternatives := ready[1:]
		if len(alternatives) > 3 {
			alternatives = alternatives[:3]
		}
		c.bus.Publish(eventbus.Event{
			Type: eventbus.NextTopic, Source: "CurriculumAgent",
			LearnerID: learnerID,
			Data: map[string]interface{}{
				"knowledge_id": nextTopic, "name": name,
				"difficulty": difficulty, "reason": "前置知识已掌握，推荐学习新内容",
				"alternatives": alternatives,
			},
		})
	}
}

func (c *CurriculumAgent) handleWeakness(event eventbus.Event) {
	knowledgeID, _ := event.Data["knowledge_id"].(string)
	masteredIDs := c.getMasteredIDs(event.LearnerID)
	remedialPath := c.knowledgeGraph.GetLearningPath(knowledgeID, masteredIDs)

	c.bus.Publish(eventbus.Event{
		Type: eventbus.PathUpdated, Source: "CurriculumAgent",
		LearnerID: event.LearnerID,
		Data: map[string]interface{}{
			"reason":            "weakness_detected",
			"weak_knowledge_id": knowledgeID,
			"remedial_path":     remedialPath,
			"message":           "检测到薄弱知识点，建议先复习前置知识",
		},
	})
}

func (c *CurriculumAgent) sendReviewSchedule(learnerID string) {
	c.mu.Lock()
	items, ok := c.reviewItems[learnerID]
	c.mu.Unlock()
	if !ok || len(items) == 0 {
		return
	}

	dueItems := model.GetDueItems(items)
	weeklySchedule := model.GetStudySchedule(items, 7)

	dueNow := make([]map[string]interface{}, 0)
	limit := 5
	if len(dueItems) < limit {
		limit = len(dueItems)
	}
	for i := 0; i < limit; i++ {
		due := dueItems[i]
		dueNow = append(dueNow, map[string]interface{}{
			"knowledge_id": due.KnowledgeID,
			"overdue_days": due.OverdueDays(),
		})
	}

	c.bus.Publish(eventbus.Event{
		Type: eventbus.ReviewScheduled, Source: "CurriculumAgent",
		LearnerID: learnerID,
		Data: map[string]interface{}{
			"due_now":         dueNow,
			"weekly_schedule": weeklySchedule,
		},
	})
}

func (c *CurriculumAgent) handlePaceAdjustment(event eventbus.Event) {
	action, _ := event.Data["action"].(string)
	reason, _ := event.Data["reason"].(string)
	log.Printf("[Curriculum] learner=%s, pace_adjustment: action=%s, reason=%s",
		event.LearnerID, action, reason)
}

func masteryToQuality(mastery float64) int {
	switch {
	case mastery >= 0.9:
		return 5
	case mastery >= 0.75:
		return 4
	case mastery >= 0.6:
		return 3
	case mastery >= 0.4:
		return 2
	case mastery >= 0.2:
		return 1
	default:
		return 0
	}
}

// ─── Hint Agent ───

type HintAgent struct {
	bus     *eventbus.EventBus
	history map[string]int
	mu      sync.Mutex
}

func NewHintAgent(bus *eventbus.EventBus) *HintAgent {
	return &HintAgent{bus: bus, history: make(map[string]int)}
}

func (h *HintAgent) Start() {
	h.bus.Subscribe(eventbus.HintNeeded, h.handleHintNeeded)
}

func (h *HintAgent) handleHintNeeded(event eventbus.Event) {
	knowledgeID, _ := event.Data["knowledge_id"].(string)
	mastery, _ := event.Data["mastery"].(float64)

	key := event.LearnerID + ":" + knowledgeID
	h.mu.Lock()
	h.history[key]++
	hintCount := h.history[key]
	h.mu.Unlock()

	level := 1
	if mastery < 0.15 && hintCount >= 3 {
		level = 3
	} else if hintCount > 3 {
		level = 3
	} else if hintCount > 1 {
		level = 2
	}

	var hintText, levelName string
	switch level {
	case 1:
		levelName = "metacognitive"
		hintText = fmt.Sprintf("💡 关于「%s」：想一想，题目里有哪些关键信息？", knowledgeID)
	case 2:
		levelName = "scaffolding"
		hintText = fmt.Sprintf("📝 关于「%s」：试着回忆相关的公式，然后一步步来。", knowledgeID)
	default:
		levelName = "targeted"
		hintText = fmt.Sprintf("📖 关于「%s」：让我帮你梳理解题思路。", knowledgeID)
	}

	log.Printf("[Hint] learner=%s, kp=%s, level=%s", event.LearnerID, knowledgeID, levelName)

	h.bus.Publish(eventbus.Event{
		Type: eventbus.HintResponse, Source: "HintAgent",
		LearnerID: event.LearnerID,
		Data: map[string]interface{}{
			"knowledge_id": knowledgeID, "hint_level": level,
			"hint_level_name": levelName, "hint_text": hintText,
		},
	})
}

// ─── Engagement Agent ───

const (
	idleThresholdSeconds     = 300
	fatigueThresholdMinutes  = 45
	fatigueAccuracyThreshold = 0.5
	boredomAccuracyThreshold = 0.9
	maxRecentItems           = 20
)

type learningState string

const (
	StateFocused     learningState = "focused"
	StateStruggling  learningState = "struggling"
	StateFrustrated  learningState = "frustrated"
	StateBored       learningState = "bored"
	StateFatigued    learningState = "fatigued"
	StateIdle        learningState = "idle"
)

type EngagementAgent struct {
	bus         *eventbus.EventBus
	engagements map[string]*learnerEngagement
	mu          sync.Mutex
}

type learnerEngagement struct {
	sessionStart       time.Time
	lastActivity       time.Time
	consecutiveErrors  int
	consecutiveCorrect int
	recentResults      []bool
	recentResponseTimes []float64
	totalInteractions  int
	encouragementCount int
	state              learningState
}

func NewEngagementAgent(bus *eventbus.EventBus) *EngagementAgent {
	return &EngagementAgent{bus: bus, engagements: make(map[string]*learnerEngagement)}
}

func (e *EngagementAgent) Start() {
	e.bus.Subscribe(eventbus.StudentSubmission, e.trackSubmission)
	e.bus.Subscribe(eventbus.AssessmentComplete, e.analyze)
}

func (e *EngagementAgent) trackSubmission(event eventbus.Event) {
	eng := e.getEngagement(event.LearnerID)
	isCorrect, ok := eventbus.DataBool(event.Data, "is_correct")
	if !ok {
		return
	}
	timeSpent, _ := event.Data["time_spent_seconds"].(float64)

	e.mu.Lock()
	defer e.mu.Unlock()

	now := time.Now()
	eng.lastActivity = now
	eng.totalInteractions++

	eng.recentResults = append(eng.recentResults, isCorrect)
	if len(eng.recentResults) > maxRecentItems {
		eng.recentResults = eng.recentResults[len(eng.recentResults)-maxRecentItems:]
	}
	eng.recentResponseTimes = append(eng.recentResponseTimes, timeSpent)
	if len(eng.recentResponseTimes) > maxRecentItems {
		eng.recentResponseTimes = eng.recentResponseTimes[len(eng.recentResponseTimes)-maxRecentItems:]
	}

	if isCorrect {
		eng.consecutiveCorrect++
		eng.consecutiveErrors = 0
	} else {
		eng.consecutiveErrors++
		eng.consecutiveCorrect = 0
	}
}

func (e *EngagementAgent) analyze(event eventbus.Event) {
	eng := e.getEngagement(event.LearnerID)

	e.mu.Lock()
	previousState := eng.state
	newState := e.detectState(eng)
	eng.state = newState
	e.mu.Unlock()

	if newState == previousState {
		return
	}

	switch newState {
	case StateFrustrated:
		e.bus.Publish(eventbus.Event{
			Type: eventbus.EngagementAlert, Source: "EngagementAgent",
			LearnerID: event.LearnerID,
			Data: map[string]interface{}{
				"alert_type":        "frustration",
				"consecutive_errors": eng.consecutiveErrors,
				"message":           "别灰心！犯错是学习的一部分。",
			},
		})
		e.bus.Publish(eventbus.Event{
			Type: eventbus.PaceAdjustment, Source: "EngagementAgent",
			LearnerID: event.LearnerID,
			Data:      map[string]interface{}{"action": "slow_down", "reason": "frustration"},
		})
	case StateBored:
		e.bus.Publish(eventbus.Event{
			Type: eventbus.EngagementAlert, Source: "EngagementAgent",
			LearnerID: event.LearnerID,
			Data: map[string]interface{}{
				"alert_type": "boredom",
				"message":    "你表现非常棒！让我们挑战更难的内容！",
			},
		})
		e.bus.Publish(eventbus.Event{
			Type: eventbus.PaceAdjustment, Source: "EngagementAgent",
			LearnerID: event.LearnerID,
			Data:      map[string]interface{}{"action": "speed_up", "reason": "boredom"},
		})
	case StateFatigued:
		sessionMin := eng.getSessionDurationMinutes()
		e.bus.Publish(eventbus.Event{
			Type: eventbus.Encouragement, Source: "EngagementAgent",
			LearnerID: event.LearnerID,
			Data: map[string]interface{}{
				"type":           "fatigue_break",
				"session_minutes": sessionMin,
				"message":        fmt.Sprintf("你已经学习了%.0f分钟，建议休息一下！", sessionMin),
			},
		})
	case StateFocused:
		if eng.consecutiveCorrect >= 3 && eng.encouragementCount%3 == 0 {
			e.bus.Publish(eventbus.Event{
				Type: eventbus.Encouragement, Source: "EngagementAgent",
				LearnerID: event.LearnerID,
				Data: map[string]interface{}{
					"message": fmt.Sprintf("连续%d题全对！继续保持！", eng.consecutiveCorrect),
					"type":    "positive_streak",
				},
			})
		}
		eng.encouragementCount++
	}

	log.Printf("[Engagement] learner=%s, state=%s -> %s", event.LearnerID, previousState, newState)
}

func (e *EngagementAgent) detectState(eng *learnerEngagement) learningState {
	if eng.getIdleSeconds() > idleThresholdSeconds {
		return StateIdle
	}
	if eng.consecutiveErrors >= 3 {
		return StateFrustrated
	}
	if eng.getSessionDurationMinutes() > fatigueThresholdMinutes &&
		eng.getRecentAccuracy() < fatigueAccuracyThreshold {
		return StateFatigued
	}
	if eng.getRecentAccuracy() > boredomAccuracyThreshold && eng.consecutiveCorrect >= 5 {
		return StateBored
	}
	if eng.consecutiveErrors >= 1 {
		return StateStruggling
	}
	return StateFocused
}

func (eng *learnerEngagement) getSessionDurationMinutes() float64 {
	return time.Since(eng.sessionStart).Minutes()
}

func (eng *learnerEngagement) getIdleSeconds() float64 {
	return time.Since(eng.lastActivity).Seconds()
}

func (eng *learnerEngagement) getRecentAccuracy() float64 {
	if len(eng.recentResults) == 0 {
		return 0.5
	}
	window := int(math.Min(10, float64(len(eng.recentResults))))
	start := len(eng.recentResults) - window
	correct := 0
	for _, r := range eng.recentResults[start:] {
		if r {
			correct++
		}
	}
	return float64(correct) / float64(window)
}

func (eng *learnerEngagement) getAvgResponseTime() float64 {
	if len(eng.recentResponseTimes) == 0 {
		return 0
	}
	window := int(math.Min(10, float64(len(eng.recentResponseTimes))))
	start := len(eng.recentResponseTimes) - window
	sum := 0.0
	for _, t := range eng.recentResponseTimes[start:] {
		sum += t
	}
	return sum / float64(window)
}

func (e *EngagementAgent) getEngagement(learnerID string) *learnerEngagement {
	e.mu.Lock()
	defer e.mu.Unlock()
	eng, ok := e.engagements[learnerID]
	if !ok {
		eng = &learnerEngagement{
			sessionStart: time.Now(),
			lastActivity: time.Now(),
			state:        StateFocused,
		}
		e.engagements[learnerID] = eng
	}
	return eng
}
