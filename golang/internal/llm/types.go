package llm

import "time"

// Role 消息角色 -- 对齐 Java Role 枚举
type Role string

const (
	RoleSystem    Role = "system"
	RoleUser      Role = "user"
	RoleAssistant Role = "assistant"
)

// LlmMessage 单条消息 -- 对齐 Java LlmMessage
type LlmMessage struct {
	Role    Role   `json:"role"`
	Content string `json:"content"`
}

// System 构造系统消息
func System(content string) LlmMessage {
	return LlmMessage{Role: RoleSystem, Content: content}
}

// User 构造用户消息
func User(content string) LlmMessage {
	return LlmMessage{Role: RoleUser, Content: content}
}

// Assistant 构造助手消息
func Assistant(content string) LlmMessage {
	return LlmMessage{Role: RoleAssistant, Content: content}
}

// LlmRequest LLM 请求 -- 对齐 Java LlmRequest
type LlmRequest struct {
	Messages    []LlmMessage `json:"messages"`
	Temperature float64      `json:"temperature"`
	MaxTokens   int          `json:"max_tokens"`
	Model       string       `json:"model,omitempty"`
}

// NewRequest 构造请求(单 system + user)
func NewRequest(systemPrompt, userPrompt string) LlmRequest {
	return LlmRequest{
		Messages:    []LlmMessage{System(systemPrompt), User(userPrompt)},
		Temperature: 0.7,
		MaxTokens:   1024,
	}
}

// NewRequestWithModel 构造请求(指定模型)
func NewRequestWithModel(systemPrompt, userPrompt, model string, maxTokens int) LlmRequest {
	return LlmRequest{
		Messages:    []LlmMessage{System(systemPrompt), User(userPrompt)},
		Temperature: 0.7,
		MaxTokens:   maxTokens,
		Model:       model,
	}
}

// LlmResponse LLM 响应 -- 对齐 Java LlmResponse
type LlmResponse struct {
	Content          string  `json:"content"`
	Model            string  `json:"model"`
	PromptTokens     int     `json:"prompt_tokens"`
	CompletionTokens int     `json:"completion_tokens"`
	TotalTokens      int     `json:"total_tokens"`
	FinishReason     string  `json:"finish_reason"`
	LatencyMs        float64 `json:"latency_ms"`
}

// IsError 是否错误响应
func (r LlmResponse) IsError() bool {
	return r.FinishReason == "error"
}

// ErrorResponse 构造错误响应
func ErrorResponse(msg string) LlmResponse {
	return LlmResponse{Content: msg, Model: "error", FinishReason: "error"}
}

// Metrics 记录 LLM 调用指标(供日志/监控用)
type Metrics struct {
	Provider       string
	Model          string
	LatencyMs      float64
	PromptTokens   int
	CompletionTokens int
	Success        bool
	Error          string
}

// CircuitState 熔断器状态
type CircuitState int

const (
	CircuitClosed CircuitState = iota
	CircuitOpen
)

// String 返回熔断状态描述
func (s CircuitState) String() string {
	switch s {
	case CircuitClosed:
		return "closed"
	case CircuitOpen:
		return "open"
	default:
		return "unknown"
	}
}

// SleepDuration 指数退避计算: 返回第 attempt 次等待时间 (1s, 2s, 4s...)
func SleepDuration(backoff time.Duration, attempt int) time.Duration {
	return backoff * time.Duration(1<<(attempt-1))
}
