package llm

import "context"

// LlmProvider 接口 -- 对齐 Java LlmProvider
//
// 实现类需处理:
// - HTTP 调用 OpenAI 兼容 API
// - 响应解析(JSON -> LlmResponse)
// - 错误处理(网络/超时/HTTP 错误)
//
// 重试与熔断由 LlmService 统一处理,provider 只需单次调用。
type LlmProvider interface {
	// Chat 执行单次 LLM 调用
	Chat(ctx context.Context, req LlmRequest) (LlmResponse, error)

	// IsAvailable 是否可用(API key 已配置且未熔断)
	IsAvailable() bool

	// Name 返回 provider 名称("openai" / "mock")
	Name() string
}
