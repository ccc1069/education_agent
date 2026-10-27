package llm

import (
	"context"
	"log"
	"strings"
)

// MockLlmProvider Mock LLM Provider -- 对齐 Java MockLlmProvider
//
// 返回可解析的 JSON(Critic/Question/Debate 场景)或固定文本(Tutor/Hint 场景),
// 标记 IsAvailable()=false,让调用方走降级逻辑。
type MockLlmProvider struct{}

// NewMockLlmProvider 创建 Mock provider
func NewMockLlmProvider() *MockLlmProvider {
	return &MockLlmProvider{}
}

// Chat 根据 system prompt 内容判断场景,返回对应格式的 mock 响应
func (p *MockLlmProvider) Chat(ctx context.Context, req LlmRequest) (LlmResponse, error) {
	systemPrompt := ""
	for _, msg := range req.Messages {
		if msg.Role == RoleSystem {
			systemPrompt = msg.Content
			break
		}
	}
	systemLower := strings.ToLower(systemPrompt)

	var content string
	switch {
	case strings.Contains(systemLower, "critic") || strings.Contains(systemLower, "评审") || strings.Contains(systemLower, "评分"):
		content = mockCriticJson()
	case strings.Contains(systemLower, "question") || strings.Contains(systemLower, "出题") || strings.Contains(systemLower, "题目"):
		content = mockQuestionJson()
	case strings.Contains(systemLower, "debate") || strings.Contains(systemLower, "辩论") || strings.Contains(systemLower, "辩手"):
		content = mockDebateJson()
	case strings.Contains(systemLower, "synthesizer") || strings.Contains(systemLower, "综合"):
		content = mockSynthesizerJson()
	default:
		// Tutor / Hint 场景:返回固定引导文本
		content = "让我们从基础概念开始思考。你能用自己的话解释一下这个知识点的核心含义吗?"
	}

	log.Printf("[MockLlmProvider] 返回 mock 响应,场景=%s", detectScene(systemLower))

	return LlmResponse{
		Content:      content,
		Model:        "mock",
		FinishReason: "stop",
	}, nil
}

// IsAvailable Mock provider 永远标记为不可用,强制调用方降级
func (p *MockLlmProvider) IsAvailable() bool {
	return false
}

// Name 返回 provider 名称
func (p *MockLlmProvider) Name() string {
	return "mock"
}

// mockCriticJson Critic 场景 mock JSON
func mockCriticJson() string {
	return `{"scores":{"pedagogical":4.0,"appropriateness":4.5,"clarity":4.0,"engagement":3.5},"overall":4.0,"critique":"该回答结构清晰,概念准确,但可补充具体实例以增强说服力。","needs_regeneration":false}`
}

// mockQuestionJson Question 场景 mock JSON
func mockQuestionJson() string {
	return `{"stem":"下列哪项最能描述苏格拉底式教学法的核心?","options":["A. 直接讲授标准答案","B. 通过连续提问引导学生自主发现","C. 让学生反复练习同类题目","D. 用多媒体展示抽象概念"],"correct_answer":"B","explanation":"苏格拉底式教学法的核心是通过一系列层层递进的问题,激发学生思考,而非直接给出结论。","difficulty":"medium","knowledge_point_id":null}`
}

// mockDebateJson Debate 场景 mock JSON
func mockDebateJson() string {
	return `{"stance":"synthesize","argument":"综合双方观点:苏格拉底式教学法在培养高阶思维方面具有显著优势,但需要根据学生认知水平灵活调整提问梯度。"}`
}

// mockSynthesizerJson Synthesizer 场景 mock JSON
func mockSynthesizerJson() string {
	return `{"consensus":"两种教学方式各有优势","remaining_disagreements":"在低龄段是否适用苏格拉底式仍存分歧","synthesis":"综合结论:苏格拉底式教学法在培养高阶思维方面具有显著优势,但需要根据学生认知水平灵活调整提问梯度。直接讲授式在基础知识传授上效率更高。两者应结合使用。","future_directions":"未来可探究不同年龄段的最佳混合比例。"}`
}

// detectScene 根据 system prompt 判断场景
func detectScene(systemPrompt string) string {
	systemLower := strings.ToLower(systemPrompt)
	switch {
	case strings.Contains(systemLower, "critic") || strings.Contains(systemLower, "评审"):
		return "critic"
	case strings.Contains(systemLower, "question") || strings.Contains(systemLower, "出题"):
		return "question"
	case strings.Contains(systemLower, "debate") || strings.Contains(systemLower, "辩手"):
		return "debate"
	case strings.Contains(systemLower, "synthesizer") || strings.Contains(systemLower, "综合"):
		return "synthesizer"
	default:
		return "tutor/hint"
	}
}
