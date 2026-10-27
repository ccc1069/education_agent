package agent

import (
	"log"

	"multi-agent-education/golang/internal/eventbus"
	"multi-agent-education/golang/internal/question"
)

// QuestionAgent 题库 Agent
//
// 面试要点:
// - 订阅 QuestionRequested 事件
// - 使用 QuestionService 生成题目
// - 发布 QuestionGenerated 事件
//
// 行为:
// 1. 收到出题请求
// 2. 调用 questionService.GenerateQuestion()
// 3. 将题目添加到题库
// 4. 发布 QuestionGenerated 事件
type QuestionAgent struct {
	bus           *eventbus.EventBus
	questionBank  *question.QuestionBank
	questionSvc   *question.QuestionService
}

// NewQuestionAgent 创建题库 Agent
func NewQuestionAgent(bus *eventbus.EventBus, questionBank *question.QuestionBank, questionSvc *question.QuestionService) *QuestionAgent {
	return &QuestionAgent{
		bus:          bus,
		questionBank: questionBank,
		questionSvc:  questionSvc,
	}
}

// Start 启动题库 Agent 事件监听
func (a *QuestionAgent) Start() {
	a.bus.Subscribe(eventbus.StudentSubmission, a.handleStudentSubmission)
	log.Println("[QuestionAgent] 已启动,订阅 StudentSubmission 事件")
}

// handleStudentSubmission 处理答题结果 (检测是否需要出新题)
func (a *QuestionAgent) handleStudentSubmission(event eventbus.Event) {
	// 检测答题是否正确,如果错误则生成新题
	isCorrect, ok := event.Data["is_correct"].(bool)
	if !ok || isCorrect {
		return
	}

	knowledgeID, ok := event.Data["knowledge_id"].(string)
	if !ok || knowledgeID == "" {
		return
	}

	// 生成题目
	q, err := a.questionSvc.GenerateQuestion(question.TypeMultipleChoice, knowledgeID, "intermediate")
	if err != nil {
		log.Printf("[QuestionAgent] 生成题目失败: %v", err)
		return
	}

	// 添加到题库
	a.questionBank.Add(*q)

	// 发布事件
	a.bus.Publish(eventbus.Event{
		Type:      eventbus.QuestionGenerated,
		Source:    "question-agent",
		LearnerID: event.LearnerID,
		Data: map[string]interface{}{
			"question_id":  q.ID,
			"knowledge_id": knowledgeID,
		},
		CorrelationID: event.CorrelationID,
	})
}
