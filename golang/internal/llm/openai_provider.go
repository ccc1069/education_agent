package llm

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
	"time"
)

// OpenAiLlmProvider OpenAI 兼容 API Provider -- 对齐 Java OpenAiLlmProvider
//
// 支持任意 OpenAI 兼容服务:
// - OpenAI 官方: https://api.openai.com/v1
// - 通义千问(DashScope): https://dashscope.aliyuncs.com/compatible-mode/v1
// - 本地 Ollama: http://localhost:11434/v1
// - vLLM / Together AI 等
//
// 使用 net/http (纯标准库,同步调用)
type OpenAiLlmProvider struct {
	apiKey      string
	baseURL     string
	defaultModel string
	maxTokens   int
	temperature float64
	httpClient  *http.Client
}

// NewOpenAiLlmProvider 创建 OpenAI provider
func NewOpenAiLlmProvider(apiKey, baseURL, defaultModel string, timeoutSec int) *OpenAiLlmProvider {
	if baseURL != "" && strings.HasSuffix(baseURL, "/") {
		baseURL = baseURL[:len(baseURL)-1]
	}
	return &OpenAiLlmProvider{
		apiKey:       apiKey,
		baseURL:      baseURL,
		defaultModel: defaultModel,
		httpClient:   &http.Client{Timeout: time.Duration(timeoutSec) * time.Second},
	}
}

// Chat 执行 LLM 调用
func (p *OpenAiLlmProvider) Chat(ctx context.Context, req LlmRequest) (LlmResponse, error) {
	if !p.IsAvailable() {
		return ErrorResponse("OpenAI API key 未配置"), errLlmUnavailable("API key 未配置", false)
	}

	model := req.Model
	if model == "" {
		model = p.defaultModel
	}

	// 构造请求体
	bodyMap := map[string]interface{}{
		"model":       model,
		"temperature": req.Temperature,
		"max_tokens":  req.MaxTokens,
		"stream":      false,
		"messages":    req.Messages,
	}

	bodyBytes, err := json.Marshal(bodyMap)
	if err != nil {
		return ErrorResponse(err.Error()), errLlmUnavailable("请求序列化失败: "+err.Error(), false)
	}

	start := time.Now()

	// 构造请求
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		p.baseURL+"/chat/completions", bytes.NewReader(bodyBytes))
	if err != nil {
		return ErrorResponse(err.Error()), errLlmUnavailable("构造请求失败: "+err.Error(), false)
	}
	httpReq.Header.Set("Authorization", "Bearer "+p.apiKey)
	httpReq.Header.Set("Content-Type", "application/json")

	// 执行请求
	resp, err := p.httpClient.Do(httpReq)
	if err != nil {
		latency := time.Since(start).Milliseconds()
		retryable := isNetworkError(err)
		log.Printf("[OpenAiLlmProvider] 网络错误: %v (latency=%dms)", err, latency)
		return ErrorResponse(err.Error()), errLlmUnavailable("网络错误: "+err.Error(), retryable)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return ErrorResponse(err.Error()), errLlmUnavailable("读取响应失败: "+err.Error(), true)
	}

	latencyMs := float64(time.Since(start).Milliseconds())

	// HTTP 错误处理
	if resp.StatusCode >= 400 {
		retryable := resp.StatusCode == 429 || resp.StatusCode >= 500
		log.Printf("[OpenAiLlmProvider] HTTP error: status=%d body=%s", resp.StatusCode,
			truncateString(string(respBody), 200))
		return ErrorResponse(fmt.Sprintf("HTTP %d", resp.StatusCode)),
			errLlmUnavailable(fmt.Sprintf("HTTP %d", resp.StatusCode), retryable)
	}

	// 解析响应
	return parseOpenAIResponse(string(respBody), latencyMs, p.defaultModel)
}

// IsAvailable 检查 API key 是否配置
func (p *OpenAiLlmProvider) IsAvailable() bool {
	return p.apiKey != "" && strings.TrimSpace(p.apiKey) != ""
}

// Name 返回 provider 名称
func (p *OpenAiLlmProvider) Name() string {
	return "openai"
}

// parseOpenAIResponse 解析 OpenAI /chat/completions 响应
func parseOpenAIResponse(body string, latencyMs float64, defaultModel string) (LlmResponse, error) {
	var root struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
			FinishReason string `json:"finish_reason"`
		} `json:"choices"`
		Model string `json:"model"`
		Usage struct {
			PromptTokens     int `json:"prompt_tokens"`
			CompletionTokens int `json:"completion_tokens"`
			TotalTokens      int `json:"total_tokens"`
		} `json:"usage"`
	}
	if err := json.Unmarshal([]byte(body), &root); err != nil {
		return ErrorResponse(err.Error()), errLlmUnavailable("响应 JSON 解析失败: "+err.Error(), false)
	}

	if len(root.Choices) == 0 {
		return ErrorResponse("响应无 choices"), errLlmUnavailable("响应无 choices", false)
	}

	choice := root.Choices[0]
	content := choice.Message.Content
	finishReason := choice.FinishReason
	model := root.Model
	if model == "" {
		model = defaultModel
	}

	promptTokens := root.Usage.PromptTokens
	completionTokens := root.Usage.CompletionTokens
	totalTokens := root.Usage.TotalTokens
	if totalTokens == 0 {
		totalTokens = promptTokens + completionTokens
	}

	return LlmResponse{
		Content:          content,
		Model:            model,
		PromptTokens:     promptTokens,
		CompletionTokens: completionTokens,
		TotalTokens:      totalTokens,
		FinishReason:     finishReason,
		LatencyMs:        latencyMs,
	}, nil
}

// isNetworkError 判断是否为可重试的网络错误
func isNetworkError(err error) bool {
	if err == nil {
		return false
	}
	errStr := err.Error()
	return strings.Contains(errStr, "timeout") ||
		strings.Contains(errStr, "connection") ||
		strings.Contains(errStr, "网络") ||
		strings.Contains(errStr, "EOF")
}

// truncateString 截断字符串(字节级)
func truncateString(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen] + "..."
}

// errLlmUnavailable 构造 LLM 不可用错误
func errLlmUnavailable(msg string, retryable bool) error {
	return &LlmUnavailableError{Message: msg, Retryable: retryable}
}

// LlmUnavailableError LLM 不可用错误 -- 对齐 Java LlmUnavailableException
type LlmUnavailableError struct {
	Message   string
	Retryable bool
}

func (e *LlmUnavailableError) Error() string {
	return e.Message
}

// IsRetryable 是否可重试
func (e *LlmUnavailableError) IsRetryable() bool {
	return e.Retryable
}
