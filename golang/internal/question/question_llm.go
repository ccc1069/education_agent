package question

import (
	"fmt"
	"strings"

	"multi-agent-education/golang/internal/llm"
)

// QuestionService 题目服务
//
// 面试要点:
// - LLM 出题 + 启发式降级
// - 支持 4 种题型
type QuestionService struct {
	llm  *llm.LlmService
	bank *QuestionBank
}

// NewQuestionService 创建题目服务
func NewQuestionService(llmService *llm.LlmService, bank *QuestionBank) *QuestionService {
	return &QuestionService{
		llm:  llmService,
		bank: bank,
	}
}

// GenerateQuestion 生成题目
//
// 优先使用 LLM,不可用时降级到启发式模板
func (s *QuestionService) GenerateQuestion(qType QuestionType, knowledgeID, level string) (*Question, error) {
	if s.llm != nil && s.llm.IsRealLlmEnabled() {
		return s.generateWithLLM(qType, knowledgeID, level)
	}
	return s.generateHeuristic(qType, knowledgeID, level), nil
}

// generateWithLLM 使用 LLM 生成题目
func (s *QuestionService) generateWithLLM(qType QuestionType, knowledgeID, level string) (*Question, error) {
	prompt := fmt.Sprintf(`请基于知识点 "%s" 生成一道 %s 难度的 %s 题目。
返回 JSON 格式: {"stem":"...","options":["A","B","C","D"],"answer":"A","explanation":"..."}`,
		knowledgeID, level, qType)

	resp := s.llm.ChatOrFallback(nil, llm.LlmRequest{
		Messages: []llm.LlmMessage{
			{Role: llm.RoleSystem, Content: "你是一位专业的出题专家。"},
			{Role: llm.RoleUser, Content: prompt},
		},
	})

	if resp == nil {
		return s.generateHeuristic(qType, knowledgeID, level), nil
	}

	// 简化: 解析失败则降级
	q := s.generateHeuristic(qType, knowledgeID, level)
	q.Metadata = map[string]interface{}{"llm_response": resp.Content}
	return q, nil
}

// generateHeuristic 启发式生成题目 (降级)
func (s *QuestionService) generateHeuristic(qType QuestionType, knowledgeID, level string) *Question {
	q := &Question{
		Type:        qType,
		KnowledgeID: knowledgeID,
		Difficulty:  levelToDifficulty(level),
		Status:      StatusDraft,
	}

	switch qType {
	case TypeMultipleChoice:
		q.Stem = fmt.Sprintf("关于「%s」,以下说法正确的是?", knowledgeID)
		q.Options = []string{"A. 选项A", "B. 选项B", "C. 选项C", "D. 选项D"}
		q.Answer = "A"
		q.Explanation = fmt.Sprintf("这是一道关于%s的选择题。", knowledgeID)
	case TypeTrueFalse:
		q.Stem = fmt.Sprintf("判断:「%s」是一个重要的知识点。", knowledgeID)
		q.Answer = "正确"
		q.Explanation = fmt.Sprintf("考察对%s的理解。", knowledgeID)
	case TypeFillBlank:
		q.Stem = fmt.Sprintf("%s是学习中的重要概念。", "___")
		q.Answer = knowledgeID
		q.Explanation = fmt.Sprintf("应填写%s。", knowledgeID)
	case TypeOpenEnded:
		q.Stem = fmt.Sprintf("请简述%s的核心内容。", knowledgeID)
		q.Answer = fmt.Sprintf("参考答案:%s的核心要点...", knowledgeID)
		q.Explanation = "开放性题目,言之有理即可。"
	}

	return q
}

// CheckAnswer 检查答案
func (s *QuestionService) CheckAnswer(questionID, userAnswer string) (correct bool, feedback string, err error) {
	q, ok := s.bank.Get(questionID)
	if !ok {
		return false, "", fmt.Errorf("question not found: %s", questionID)
	}

	// 简单字符串比较 (忽略大小写和空白)
	correct = strings.TrimSpace(strings.ToLower(userAnswer)) == strings.TrimSpace(strings.ToLower(q.Answer))

	if correct {
		feedback = "回答正确!" + " " + q.Explanation
	} else {
		feedback = fmt.Sprintf("回答错误。正确答案是: %s。%s", q.Answer, q.Explanation)
	}

	return correct, feedback, nil
}

// levelToDifficulty 将水平转换为难度 1-5
func levelToDifficulty(level string) int {
	switch strings.ToLower(level) {
	case "beginner":
		return 1
	case "elementary":
		return 2
	case "intermediate":
		return 3
	case "advanced":
		return 4
	case "expert":
		return 5
	default:
		return 3
	}
}
