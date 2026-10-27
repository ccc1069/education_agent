package model

import (
	"math"
	"sort"
	"sync"
	"time"
)

// KnowledgeState 单个知识点的掌握状态
type KnowledgeState struct {
	KnowledgeID  string    `json:"knowledge_id"`
	Mastery      float64   `json:"mastery"`
	Attempts     int       `json:"attempts"`
	CorrectCount int       `json:"correct_count"`
	Streak       int       `json:"streak"`
	LastAttempt  time.Time `json:"last_attempt"`
	Version      int       `json:"version"`
}

// Level 返回掌握等级
func (s *KnowledgeState) Level() string {
	if s.Attempts == 0 {
		return "not_started"
	}
	switch {
	case s.Mastery < 0.3:
		return "beginner"
	case s.Mastery < 0.6:
		return "developing"
	case s.Mastery < 0.85:
		return "proficient"
	default:
		return "mastered"
	}
}

// BKT 参数
const (
	pInit    = 0.1
	pTransit = 0.15
	pGuess   = 0.2
	pSlip    = 0.1
)

// LearnerModel 学习者模型 -- BKT实现
type LearnerModel struct {
	LearnerID string
	states    map[string]*KnowledgeState
	mu        sync.RWMutex
}

// NewLearnerModel 创建学习者模型
func NewLearnerModel(learnerID string) *LearnerModel {
	return &LearnerModel{
		LearnerID: learnerID,
		states:    make(map[string]*KnowledgeState),
	}
}

// GetState 获取知识点状态
func (m *LearnerModel) GetState(knowledgeID string) *KnowledgeState {
	m.mu.Lock()
	defer m.mu.Unlock()
	s, ok := m.states[knowledgeID]
	if !ok {
		s = &KnowledgeState{KnowledgeID: knowledgeID, Mastery: pInit}
		m.states[knowledgeID] = s
	}
	return s
}

// UpdateMastery BKT核心算法
func (m *LearnerModel) UpdateMastery(knowledgeID string, isCorrect bool) *KnowledgeState {
	state := m.GetState(knowledgeID)
	pL := state.Mastery

	var pObsGivenL, pObsGivenNotL float64
	if isCorrect {
		pObsGivenL = 1 - pSlip
		pObsGivenNotL = pGuess
		state.CorrectCount++
		state.Streak++
	} else {
		pObsGivenL = pSlip
		pObsGivenNotL = 1 - pGuess
		state.Streak = 0
	}

	pObs := pL*pObsGivenL + (1-pL)*pObsGivenNotL
	pLGivenObs := pL
	if pObs > 0 {
		pLGivenObs = (pL * pObsGivenL) / pObs
	}
	pLNew := pLGivenObs + (1-pLGivenObs)*pTransit

	state.Mastery = math.Max(0, math.Min(1, pLNew))
	state.Attempts++
	state.LastAttempt = time.Now()
	return state
}

// PutState 从持久化恢复知识点状态。
func (m *LearnerModel) PutState(state *KnowledgeState) {
	if state == nil {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	cp := *state
	m.states[state.KnowledgeID] = &cp
}

// GetAllStates 获取所有知识点状态
func (m *LearnerModel) GetAllStates() []KnowledgeState {
	m.mu.RLock()
	defer m.mu.RUnlock()
	result := make([]KnowledgeState, 0, len(m.states))
	for _, s := range m.states {
		result = append(result, *s)
	}
	return result
}

// GetWeakPoints 获取薄弱知识点
func (m *LearnerModel) GetWeakPoints(threshold float64) []*KnowledgeState {
	m.mu.RLock()
	defer m.mu.RUnlock()
	var weak []*KnowledgeState
	for _, s := range m.states {
		if s.Mastery < threshold && s.Attempts > 0 {
			weak = append(weak, s)
		}
	}
	return weak
}

// ReviewItem SM-2复习条目
type ReviewItem struct {
	KnowledgeID    string    `json:"knowledge_id"`
	EasinessFactor float64   `json:"easiness_factor"`
	IntervalDays   float64   `json:"interval_days"`
	Repetition     int       `json:"repetition"`
	NextReview     time.Time `json:"next_review"`
}

// NewReviewItem 创建复习条目
func NewReviewItem(knowledgeID string) *ReviewItem {
	return &ReviewItem{
		KnowledgeID:    knowledgeID,
		EasinessFactor: 2.5,
		NextReview:     time.Now(),
	}
}

// SM2Review SM-2算法核心
func SM2Review(item *ReviewItem, quality int) {
	if quality < 0 {
		quality = 0
	}
	if quality > 5 {
		quality = 5
	}

	newEF := item.EasinessFactor + (0.1 - float64(5-quality)*(0.08+float64(5-quality)*0.02))
	item.EasinessFactor = math.Max(1.3, math.Min(2.5, newEF))

	if quality < 3 {
		item.Repetition = 0
		item.IntervalDays = 1
	} else {
		switch item.Repetition {
		case 0:
			item.IntervalDays = 1
		case 1:
			item.IntervalDays = 6
		default:
			item.IntervalDays = item.IntervalDays * item.EasinessFactor
		}
		item.Repetition++
	}

	item.NextReview = time.Now().Add(time.Duration(item.IntervalDays*24) * time.Hour)
}

// IsDue 判断是否到期
func (r *ReviewItem) IsDue() bool {
	return time.Now().After(r.NextReview)
}

// OverdueDays 返回逾期天数
func (r *ReviewItem) OverdueDays() int {
	if r.IsDue() {
		return int(time.Since(r.NextReview).Hours() / 24)
	}
	return 0
}

// GetDueItems 获取到期需复习的知识点，按逾期天数降序排列
func GetDueItems(items map[string]*ReviewItem) []*ReviewItem {
	var due []*ReviewItem
	for _, item := range items {
		if item.IsDue() {
			due = append(due, item)
		}
	}
	sort.Slice(due, func(i, j int) bool {
		return due[i].OverdueDays() > due[j].OverdueDays()
	})
	return due
}

// GetStudySchedule 生成未来 N 天的学习计划
func GetStudySchedule(items map[string]*ReviewItem, daysAhead int) map[string][]string {
	schedule := make(map[string][]string)
	today := time.Now().Truncate(24 * time.Hour)

	for i := 0; i < daysAhead; i++ {
		date := today.AddDate(0, 0, i)
		dateKey := date.Format("2006-01-02")
		var dueIDs []string

		for id, item := range items {
			reviewDate := item.NextReview.Truncate(24 * time.Hour)
			if !reviewDate.After(date) {
				dueIDs = append(dueIDs, id)
			}
		}

		if len(dueIDs) > 0 {
			schedule[dateKey] = dueIDs
		}
	}

	return schedule
}
