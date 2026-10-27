package question

import (
	"testing"
)

func TestCanTransition(t *testing.T) {
	tests := []struct {
		from, to QuestionStatus
		want     bool
	}{
		{StatusDraft, StatusReview, true},
		{StatusReview, StatusPublished, true},
		{StatusReview, StatusRejected, true},
		{StatusPublished, StatusArchived, true},
		{StatusRejected, StatusDraft, true},
		// 非法转换
		{StatusDraft, StatusPublished, false},
		{StatusPublished, StatusReview, false},
		{StatusArchived, StatusDraft, false},
	}
	for _, tt := range tests {
		got := CanTransition(tt.from, tt.to)
		if got != tt.want {
			t.Errorf("CanTransition(%s, %s) = %v, want %v", tt.from, tt.to, got, tt.want)
		}
	}
}

func TestQuestionBank_AddAndGet(t *testing.T) {
	bank := NewQuestionBank()

	q := Question{
		Type:        TypeMultipleChoice,
		Stem:        "测试题目",
		Answer:      "A",
		KnowledgeID: "math-001",
		Status:      StatusDraft,
	}

	if err := bank.Add(q); err != nil {
		t.Fatalf("Add failed: %v", err)
	}

	if bank.Count() != 1 {
		t.Errorf("count: got %d, want 1", bank.Count())
	}

	got, ok := bank.Get(q.ID)
	if ok {
		t.Error("should not get without ID")
	}

	// 使用生成的 ID 重新添加
	q.ID = "test-q-1"
	bank.Add(q)
	got, ok = bank.Get("test-q-1")
	if !ok {
		t.Error("should get question by ID")
	}
	if got.Stem != "测试题目" {
		t.Errorf("stem: got %s, want 测试题目", got.Stem)
	}
}

func TestQuestionBank_UpdateStatus(t *testing.T) {
	bank := NewQuestionBank()

	q := Question{ID: "q1", Status: StatusDraft}
	bank.Add(q)

	// 合法: draft -> review
	if err := bank.UpdateStatus("q1", StatusReview); err != nil {
		t.Errorf("draft->review should succeed: %v", err)
	}

	// 合法: review -> published
	if err := bank.UpdateStatus("q1", StatusPublished); err != nil {
		t.Errorf("review->published should succeed: %v", err)
	}

	// 非法: published -> review
	if err := bank.UpdateStatus("q1", StatusReview); err == nil {
		t.Error("published->review should fail")
	}
}

func TestQuestionBank_ListByKnowledge(t *testing.T) {
	bank := NewQuestionBank()

	bank.Add(Question{ID: "q1", KnowledgeID: "math", Status: StatusPublished})
	bank.Add(Question{ID: "q2", KnowledgeID: "math", Status: StatusDraft})
	bank.Add(Question{ID: "q3", KnowledgeID: "english", Status: StatusPublished})

	// math 知识点
	mathQs := bank.ListByKnowledge("math", "")
	if len(mathQs) != 2 {
		t.Errorf("math questions: got %d, want 2", len(mathQs))
	}

	// 仅 published
	pubQs := bank.ListByKnowledge("math", StatusPublished)
	if len(pubQs) != 1 {
		t.Errorf("published math questions: got %d, want 1", len(pubQs))
	}
}

func TestQuestionService_GenerateHeuristic(t *testing.T) {
	bank := NewQuestionBank()
	service := NewQuestionService(nil, bank)

	tests := []struct {
		qType QuestionType
	}{
		{TypeMultipleChoice},
		{TypeTrueFalse},
		{TypeFillBlank},
		{TypeOpenEnded},
	}

	for _, tt := range tests {
		q, err := service.GenerateQuestion(tt.qType, "test-knowledge", "intermediate")
		if err != nil {
			t.Errorf("GenerateQuestion(%s) error: %v", tt.qType, err)
			continue
		}
		if q.Stem == "" {
			t.Errorf("%s: stem should not be empty", tt.qType)
		}
		if q.Status != StatusDraft {
			t.Errorf("%s: status should be draft", tt.qType)
		}
	}
}

func TestQuestionService_CheckAnswer(t *testing.T) {
	bank := NewQuestionBank()
	service := NewQuestionService(nil, bank)

	q := Question{
		ID:     "q1",
		Answer: "A",
	}
	bank.Add(q)

	// 正确
	correct, feedback, err := service.CheckAnswer("q1", "A")
	if err != nil {
		t.Fatalf("CheckAnswer failed: %v", err)
	}
	if !correct {
		t.Error("should be correct")
	}
	if feedback == "" {
		t.Error("feedback should not be empty")
	}

	// 错误
	correct, _, _ = service.CheckAnswer("q1", "B")
	if correct {
		t.Error("should be incorrect")
	}

	// 不存在
	_, _, err = service.CheckAnswer("nonexistent", "A")
	if err == nil {
		t.Error("should fail for nonexistent question")
	}
}

func TestLevelToDifficulty(t *testing.T) {
	tests := []struct {
		level string
		want  int
	}{
		{"beginner", 1},
		{"intermediate", 3},
		{"expert", 5},
		{"unknown", 3},
	}
	for _, tt := range tests {
		got := levelToDifficulty(tt.level)
		if got != tt.want {
			t.Errorf("levelToDifficulty(%s) = %d, want %d", tt.level, got, tt.want)
		}
	}
}
