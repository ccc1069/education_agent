package question

import (
	"crypto/rand"
	"fmt"
	"sync"
	"time"
)

// QuestionType 题目类型
type QuestionType string

const (
	TypeMultipleChoice QuestionType = "multiple_choice"
	TypeFillBlank      QuestionType = "fill_blank"
	TypeTrueFalse     QuestionType = "true_false"
	TypeOpenEnded     QuestionType = "open_ended"
)

// QuestionStatus 题目审核状态
type QuestionStatus string

const (
	StatusDraft     QuestionStatus = "draft"
	StatusReview    QuestionStatus = "review"
	StatusPublished QuestionStatus = "published"
	StatusRejected  QuestionStatus = "rejected"
	StatusArchived  QuestionStatus = "archived"
)

// Question 题目
type Question struct {
	ID          string                 `json:"id"`
	Type        QuestionType           `json:"type"`
	Stem        string                 `json:"stem"`
	Options     []string               `json:"options,omitempty"`
	Answer      string                 `json:"answer"`
	Explanation string                 `json:"explanation"`
	Difficulty  int                    `json:"difficulty"` // 1-5
	KnowledgeID string                 `json:"knowledge_id"`
	Status      QuestionStatus         `json:"status"`
	Metadata    map[string]interface{} `json:"metadata,omitempty"`
	CreatedAt   time.Time              `json:"created_at"`
	UpdatedAt   time.Time              `json:"updated_at"`
}

// validTransitions 状态机转换规则
var validTransitions = map[QuestionStatus]map[QuestionStatus]bool{
	StatusDraft:     {StatusReview: true},
	StatusReview:    {StatusPublished: true, StatusRejected: true},
	StatusPublished: {StatusArchived: true},
	StatusRejected:  {StatusDraft: true},
	StatusArchived:  {},
}

// CanTransition 检查状态转换是否合法
func CanTransition(from, to QuestionStatus) bool {
	if m, ok := validTransitions[from]; ok {
		return m[to]
	}
	return false
}

// QuestionBank 题库存储
type QuestionBank struct {
	mu          sync.RWMutex
	questions   map[string]Question
	byKnowledge map[string][]string // knowledgeID -> questionIDs
	onSave      func(Question) error
	onDelete    func(id string) error
}

// NewQuestionBank 创建题库
func NewQuestionBank() *QuestionBank {
	return &QuestionBank{
		questions:   make(map[string]Question),
		byKnowledge: make(map[string][]string),
	}
}

// SetPersistHooks 设置落盘钩子（写后调用，不阻塞主路径错误时仅忽略由调用方决定）
func (b *QuestionBank) SetPersistHooks(onSave func(Question) error, onDelete func(id string) error) {
	b.onSave = onSave
	b.onDelete = onDelete
}

// Import 启动加载，不触发落盘钩子
func (b *QuestionBank) Import(q Question) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.questions[q.ID] = q
	if q.KnowledgeID != "" {
		b.byKnowledge[q.KnowledgeID] = append(b.byKnowledge[q.KnowledgeID], q.ID)
	}
}

// Add 添加题目
func (b *QuestionBank) Add(q Question) error {
	b.mu.Lock()
	defer b.mu.Unlock()

	if q.ID == "" {
		q.ID = generateID()
	}
	if q.CreatedAt.IsZero() {
		q.CreatedAt = time.Now()
	}
	q.UpdatedAt = time.Now()

	b.questions[q.ID] = q
	if q.KnowledgeID != "" {
		b.byKnowledge[q.KnowledgeID] = append(b.byKnowledge[q.KnowledgeID], q.ID)
	}
	if b.onSave != nil {
		_ = b.onSave(q)
	}
	return nil
}

// Get 获取题目
func (b *QuestionBank) Get(id string) (Question, bool) {
	b.mu.RLock()
	defer b.mu.RUnlock()

	q, ok := b.questions[id]
	return q, ok
}

// UpdateStatus 更新题目状态
func (b *QuestionBank) UpdateStatus(id string, newStatus QuestionStatus) error {
	b.mu.Lock()
	defer b.mu.Unlock()

	q, ok := b.questions[id]
	if !ok {
		return fmt.Errorf("question not found: %s", id)
	}

	if !CanTransition(q.Status, newStatus) {
		return fmt.Errorf("invalid transition: %s -> %s", q.Status, newStatus)
	}

	q.Status = newStatus
	q.UpdatedAt = time.Now()
	b.questions[id] = q
	if b.onSave != nil {
		_ = b.onSave(q)
	}
	return nil
}

// ListByKnowledge 按知识点列出题目
func (b *QuestionBank) ListByKnowledge(knowledgeID string, status QuestionStatus) []Question {
	b.mu.RLock()
	defer b.mu.RUnlock()

	var result []Question
	for _, id := range b.byKnowledge[knowledgeID] {
		if q, ok := b.questions[id]; ok {
			if status == "" || q.Status == status {
				result = append(result, q)
			}
		}
	}
	return result
}

// ListAll 列出所有题目
func (b *QuestionBank) ListAll(status QuestionStatus) []Question {
	b.mu.RLock()
	defer b.mu.RUnlock()

	var result []Question
	for _, q := range b.questions {
		if status == "" || q.Status == status {
			result = append(result, q)
		}
	}
	return result
}

// Count 获取题目总数
func (b *QuestionBank) Count() int {
	b.mu.RLock()
	defer b.mu.RUnlock()
	return len(b.questions)
}

// Delete 删除题目
func (b *QuestionBank) Delete(id string) error {
	b.mu.Lock()
	defer b.mu.Unlock()

	q, ok := b.questions[id]
	if !ok {
		return fmt.Errorf("question not found: %s", id)
	}
	delete(b.questions, id)
	// 从 byKnowledge 索引中移除
	if q.KnowledgeID != "" {
		ids := b.byKnowledge[q.KnowledgeID]
		var filtered []string
		for _, qid := range ids {
			if qid != id {
				filtered = append(filtered, qid)
			}
		}
		b.byKnowledge[q.KnowledgeID] = filtered
	}
	if b.onDelete != nil {
		_ = b.onDelete(id)
	}
	return nil
}

// generateID 生成随机 ID
func generateID() string {
	b := make([]byte, 12)
	rand.Read(b)
	return fmt.Sprintf("q-%x", b)
}
