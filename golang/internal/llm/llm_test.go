package llm

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

// ─── Mock Provider 测试 ───

func TestMockProvider_Chat_CriticScenario(t *testing.T) {
	p := NewMockLlmProvider()
	resp, err := p.Chat(context.Background(), NewRequest(CriticSystemPrompt, "test"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Model != "mock" {
		t.Errorf("expected model=mock, got %s", resp.Model)
	}
	// 验证返回可解析的 JSON
	var root map[string]interface{}
	if err := json.Unmarshal([]byte(resp.Content), &root); err != nil {
		t.Fatalf("mock critic response not valid JSON: %v", err)
	}
	if _, ok := root["overall"]; !ok {
		t.Error("mock critic response missing 'overall' field")
	}
}

func TestMockProvider_Chat_TutorScenario(t *testing.T) {
	p := NewMockLlmProvider()
	resp, err := p.Chat(context.Background(), NewRequest(TutorBase, "test"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Content == "" {
		t.Error("expected non-empty content for tutor scenario")
	}
}

func TestMockProvider_IsAvailable(t *testing.T) {
	p := NewMockLlmProvider()
	if p.IsAvailable() {
		t.Error("mock provider should never be available")
	}
}

func TestMockProvider_Name(t *testing.T) {
	p := NewMockLlmProvider()
	if p.Name() != "mock" {
		t.Errorf("expected name=mock, got %s", p.Name())
	}
}

// ─── OpenAI Provider 测试 ───

func TestOpenAiProvider_Chat_Success(t *testing.T) {
	// 创建 mock OpenAI 服务器
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer test-key" {
			t.Errorf("expected Authorization header, got: %s", r.Header.Get("Authorization"))
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"choices": []map[string]interface{}{
				{"message": map[string]string{"content": "test response"}, "finish_reason": "stop"},
			},
			"model": "gpt-4o-mini",
			"usage": map[string]int{"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
		})
	}))
	defer server.Close()

	p := NewOpenAiLlmProvider("test-key", server.URL, "gpt-4o-mini", 30)
	resp, err := p.Chat(context.Background(), NewRequest("system", "hello"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Content != "test response" {
		t.Errorf("expected 'test response', got '%s'", resp.Content)
	}
	if resp.Model != "gpt-4o-mini" {
		t.Errorf("expected model=gpt-4o-mini, got %s", resp.Model)
	}
	if resp.TotalTokens != 30 {
		t.Errorf("expected 30 tokens, got %d", resp.TotalTokens)
	}
	if resp.LatencyMs < 0 {
		t.Error("expected non-negative latency")
	}
}

func TestOpenAiProvider_Chat_NoKey(t *testing.T) {
	p := NewOpenAiLlmProvider("", "https://api.openai.com/v1", "gpt-4o-mini", 30)
	_, err := p.Chat(context.Background(), NewRequest("system", "hello"))
	if err == nil {
		t.Fatal("expected error when no API key")
	}
}

func TestOpenAiProvider_Chat_ServerError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(500)
		w.Write([]byte("internal error"))
	}))
	defer server.Close()

	p := NewOpenAiLlmProvider("test-key", server.URL, "gpt-4o-mini", 30)
	_, err := p.Chat(context.Background(), NewRequest("system", "hello"))
	if err == nil {
		t.Fatal("expected error on server 500")
	}
}

func TestOpenAiProvider_IsAvailable(t *testing.T) {
	p1 := NewOpenAiLlmProvider("key", "url", "model", 30)
	if !p1.IsAvailable() {
		t.Error("provider with key should be available")
	}
	p2 := NewOpenAiLlmProvider("", "url", "model", 30)
	if p2.IsAvailable() {
		t.Error("provider without key should not be available")
	}
}

// ─── LlmService 测试 ───

// fakeProvider 用于测试的 fake provider
type fakeProvider struct {
	available    bool
	name         string
	callCount    atomic.Int32
	failCount    int // 前 N 次失败
	responseText string
}

func (f *fakeProvider) Chat(ctx context.Context, req LlmRequest) (LlmResponse, error) {
	count := f.callCount.Add(1)
	if int(count) <= f.failCount {
		return ErrorResponse("forced failure"), errLLMUnavailable("forced", true)
	}
	return LlmResponse{Content: f.responseText, Model: "test-model", TotalTokens: 10}, nil
}

func (f *fakeProvider) IsAvailable() bool { return f.available }
func (f *fakeProvider) Name() string      { return f.name }

func errLLMUnavailable(msg string, retryable bool) error {
	return &LlmUnavailableError{Message: msg, Retryable: retryable}
}

func TestLlmService_Chat_Success(t *testing.T) {
	p := &fakeProvider{available: true, name: "fake", responseText: "ok"}
	s := NewLlmServiceWithConfig(p, 3, 10*time.Millisecond, 5, 60*time.Second)

	resp, err := s.Chat(context.Background(), NewRequest("sys", "user"))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Content != "ok" {
		t.Errorf("expected 'ok', got '%s'", resp.Content)
	}
}

func TestLlmService_Chat_RetryThenSuccess(t *testing.T) {
	p := &fakeProvider{available: true, name: "fake", failCount: 2, responseText: "ok"}
	s := NewLlmServiceWithConfig(p, 3, 10*time.Millisecond, 5, 60*time.Second)

	resp, err := s.Chat(context.Background(), NewRequest("sys", "user"))
	if err != nil {
		t.Fatalf("unexpected error after retry: %v", err)
	}
	if resp.Content != "ok" {
		t.Errorf("expected 'ok', got '%s'", resp.Content)
	}
	if p.callCount.Load() != 3 {
		t.Errorf("expected 3 calls (1 fail + 1 fail + 1 success), got %d", p.callCount.Load())
	}
}

func TestLlmService_Chat_RetryExhausted(t *testing.T) {
	p := &fakeProvider{available: true, name: "fake", failCount: 10}
	s := NewLlmServiceWithConfig(p, 3, 10*time.Millisecond, 5, 60*time.Second)

	_, err := s.Chat(context.Background(), NewRequest("sys", "user"))
	if err == nil {
		t.Fatal("expected error after retry exhausted")
	}
	if p.callCount.Load() != 3 {
		t.Errorf("expected 3 calls, got %d", p.callCount.Load())
	}
}

func TestLlmService_CircuitBreaker(t *testing.T) {
	p := &fakeProvider{available: true, name: "fake", failCount: 100}
	s := NewLlmServiceWithConfig(p, 1, 1*time.Millisecond, 3, 60*time.Second)

	// 触发熔断:连续 3 次失败
	for i := 0; i < 3; i++ {
		s.Chat(context.Background(), NewRequest("sys", "user"))
	}

	if !s.IsCircuitOpen() {
		t.Error("circuit should be open after 3 failures")
	}

	// 熔断时调用应立即失败
	_, err := s.Chat(context.Background(), NewRequest("sys", "user"))
	if err == nil {
		t.Fatal("expected error when circuit open")
	}
}

func TestLlmService_ChatOrFallback(t *testing.T) {
	p := &fakeProvider{available: true, name: "fake", failCount: 100}
	s := NewLlmServiceWithConfig(p, 1, 1*time.Millisecond, 5, 60*time.Second)

	resp := s.ChatOrFallback(context.Background(), NewRequest("sys", "user"))
	if resp != nil {
		t.Error("expected nil response on failure")
	}
}

func TestLlmService_ChatString(t *testing.T) {
	p := &fakeProvider{available: true, name: "fake", responseText: "hello"}
	s := NewLlmServiceWithConfig(p, 3, 10*time.Millisecond, 5, 60*time.Second)

	content := s.ChatString(context.Background(), NewRequest("sys", "user"))
	if content != "hello" {
		t.Errorf("expected 'hello', got '%s'", content)
	}
}

// ─── Prompts 测试 ───

func TestGetTutorPrompt(t *testing.T) {
	levels := []string{"beginner", "developing", "proficient", "mastered", "unknown"}
	for _, level := range levels {
		prompt := GetTutorPrompt(level)
		if prompt == "" {
			t.Errorf("expected non-empty prompt for level %s", level)
		}
	}
}

func TestGetHintPrompt(t *testing.T) {
	for _, level := range []int{1, 2, 3, 99} {
		prompt := GetHintPrompt(level)
		if prompt == "" {
			t.Errorf("expected non-empty prompt for level %d", level)
		}
	}
}

func TestSanitize(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{"empty", "", ""},
		{"normal", "hello world", "hello world"},
		{"control chars", "hello\x00world", "helloworld"},
		{"keep newline", "hello\nworld", "hello\nworld"},
		{"keep tab", "hello\tworld", "hello\tworld"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := Sanitize(tt.input)
			if result != tt.expected {
				t.Errorf("Sanitize(%q) = %q, want %q", tt.input, result, tt.expected)
			}
		})
	}
}

func TestSanitize_Truncate(t *testing.T) {
	long := strings.Repeat("a", 5000)
	result := Sanitize(long)
	// 4000 + "...[已截断]" (12 bytes in UTF-8)
	if len(result) > 4020 {
		t.Errorf("expected truncated length <= 4020, got %d", len(result))
	}
}

func TestBuildCriticUserPrompt(t *testing.T) {
	prompt := BuildCriticUserPrompt("什么是方程？", "方程是...", "beginner")
	if !strings.Contains(prompt, "什么是方程？") {
		t.Error("prompt should contain question")
	}
	if !strings.Contains(prompt, "方程是...") {
		t.Error("prompt should contain answer")
	}
}

// ─── CriticService 测试 ───

func TestCriticService_Evaluate_Heuristic(t *testing.T) {
	// 使用总是失败的 provider → 降级到启发式
	p := &fakeProvider{available: true, name: "fake", failCount: 100}
	llm := NewLlmServiceWithConfig(p, 1, 1*time.Millisecond, 5, 60*time.Second)
	critic := NewCriticService(llm)

	result := critic.Evaluate("algebra", "beginner", 0.3, nil, "好的,让我们一起来分析这道题。", "什么是方程？")
	if result == nil {
		t.Fatal("expected non-nil result")
	}
	if result.Model != "heuristic" {
		t.Errorf("expected heuristic model, got %s", result.Model)
	}
	if result.Overall < 1 || result.Overall > 5 {
		t.Errorf("overall out of range: %f", result.Overall)
	}
}

func TestCriticService_Evaluate_EmptyResponse(t *testing.T) {
	p := &fakeProvider{available: true, name: "fake", failCount: 100}
	llm := NewLlmServiceWithConfig(p, 1, 1*time.Millisecond, 5, 60*time.Second)
	critic := NewCriticService(llm)

	result := critic.Evaluate("algebra", "beginner", 0.3, nil, "", "什么是方程？")
	if result == nil {
		t.Fatal("expected non-nil result")
	}
	if !result.NeedsRegeneration {
		t.Error("empty response should need regeneration")
	}
}

func TestCriticService_Regenerate_Fallback(t *testing.T) {
	p := &fakeProvider{available: true, name: "fake", failCount: 100}
	llm := NewLlmServiceWithConfig(p, 1, 1*time.Millisecond, 5, 60*time.Second)
	critic := NewCriticService(llm)

	original := "原回复内容"
	result := critic.Regenerate("algebra", "beginner", 0.3, nil, original, "需要改进", "什么是方程？")
	if result == nil {
		t.Fatal("expected non-nil result")
	}
	if result.Text != original {
		t.Errorf("expected original text on fallback, got %s", result.Text)
	}
}

func TestCriticService_Evaluate_WithMockLlm(t *testing.T) {
	// 使用 mock provider (返回有效 JSON) → 正常解析
	p := NewMockLlmProvider()
	llm := NewLlmServiceWithConfig(p, 1, 1*time.Millisecond, 5, 60*time.Second)
	critic := NewCriticService(llm)

	result := critic.Evaluate("algebra", "beginner", 0.3, nil, "test response", "什么是方程？")
	if result == nil {
		t.Fatal("expected non-nil result")
	}
	// mock provider 返回 critic JSON,应成功解析
	if result.Model != "mock" {
		t.Errorf("expected mock model, got %s", result.Model)
	}
	if result.Overall < 1 || result.Overall > 5 {
		t.Errorf("overall out of range: %f", result.Overall)
	}
}

// ─── DebateService 测试 ───

func TestDebateService_RunDebate_Heuristic(t *testing.T) {
	// 使用总是失败的 provider → 降级到启发式
	p := &fakeProvider{available: true, name: "fake", failCount: 100}
	llm := NewLlmServiceWithConfig(p, 1, 1*time.Millisecond, 5, 60*time.Second)
	debate := NewDebateService(llm, 2)

	result := debate.RunDebate("algebra", "beginner", 0.3, "什么是方程？")
	if result == nil {
		t.Fatal("expected non-nil result")
	}
	if result.Consensus == "" {
		t.Error("expected non-empty consensus")
	}
	if result.Metadata["llm_used"] != false {
		t.Error("expected heuristic fallback (llm_used=false)")
	}
}

func TestDebateService_RunDebate_WithMockLlm(t *testing.T) {
	// 使用 mock provider (返回有效 JSON) → 正常辩论
	p := NewMockLlmProvider()
	llm := NewLlmServiceWithConfig(p, 1, 1*time.Millisecond, 5, 60*time.Second)
	debate := NewDebateService(llm, 2)

	result := debate.RunDebate("algebra", "beginner", 0.3, "什么是方程？")
	if result == nil {
		t.Fatal("expected non-nil result")
	}
	if result.Consensus == "" {
		t.Error("expected non-empty consensus")
	}
	// mock provider 返回有效 JSON,应走 LLM 路径
	if result.Metadata["llm_used"] != true {
		t.Error("expected LLM path (llm_used=true)")
	}
}

func TestDebateService_DefaultRounds(t *testing.T) {
	p := NewMockLlmProvider()
	llm := NewLlmServiceWithConfig(p, 1, 1*time.Millisecond, 5, 60*time.Second)

	debate1 := NewDebateService(llm, 0)
	if debate1.rounds != 2 {
		t.Errorf("expected default 2 rounds, got %d", debate1.rounds)
	}

	debate2 := NewDebateService(llm, 10)
	if debate2.rounds != 4 {
		t.Errorf("expected max 4 rounds, got %d", debate2.rounds)
	}
}

// ─── Factory 测试 ───

func TestFactory_AutoMode_NoKey(t *testing.T) {
	p := NewOpenAiLlmProvider("", "https://api.openai.com/v1", "gpt-4o-mini", 30)
	mock := NewMockLlmProvider()
	factory := NewLlmProviderFactoryWithProviders(p, mock, "auto")

	provider := factory.GetProvider()
	if provider.Name() != "mock" {
		t.Errorf("expected mock provider when no key, got %s", provider.Name())
	}
	if factory.IsRealLlmEnabled() {
		t.Error("should not be real LLM enabled without key")
	}
}

func TestFactory_AutoMode_WithKey(t *testing.T) {
	p := NewOpenAiLlmProvider("test-key", "https://api.openai.com/v1", "gpt-4o-mini", 30)
	mock := NewMockLlmProvider()
	factory := NewLlmProviderFactoryWithProviders(p, mock, "auto")

	provider := factory.GetProvider()
	if provider.Name() != "openai" {
		t.Errorf("expected openai provider when key present, got %s", provider.Name())
	}
	if !factory.IsRealLlmEnabled() {
		t.Error("should be real LLM enabled with key")
	}
}

func TestFactory_MockMode(t *testing.T) {
	p := NewOpenAiLlmProvider("test-key", "https://api.openai.com/v1", "gpt-4o-mini", 30)
	mock := NewMockLlmProvider()
	factory := NewLlmProviderFactoryWithProviders(p, mock, "mock")

	provider := factory.GetProvider()
	if provider.Name() != "mock" {
		t.Errorf("expected mock provider, got %s", provider.Name())
	}
}

// ─── JSON 解析测试 ───

func TestParseCriticJson(t *testing.T) {
	jsonStr := `{"scores":{"pedagogical":4.0,"appropriateness":4.5,"clarity":4.0,"engagement":3.5},"overall":4.0,"critique":"good","needs_regeneration":false}`
	result := parseCriticJson(jsonStr, "test-model", 10)
	if result == nil {
		t.Fatal("expected non-nil result")
	}
	if result.Overall != 4.0 {
		t.Errorf("expected overall=4.0, got %f", result.Overall)
	}
	if result.Critique != "good" {
		t.Errorf("expected critique='good', got '%s'", result.Critique)
	}
	if result.NeedsRegeneration {
		t.Error("should not need regeneration for overall=4.0")
	}
}

func TestParseCriticJson_OverallEquals3DefaultNeedsRegen(t *testing.T) {
	// 对齐 Python: needs_regeneration 缺省时 overall <= 3 → true
	jsonStr := `{"scores":{"pedagogical":3,"appropriateness":3,"clarity":3,"engagement":3},"overall":3,"critique":"borderline"}`
	result := parseCriticJson(jsonStr, "test-model", 10)
	if result == nil {
		t.Fatal("expected non-nil result")
	}
	if !result.NeedsRegeneration {
		t.Error("overall==3 without needs_regeneration field must need regeneration (Py default)")
	}
}

func TestParseCriticJson_ExplicitFalseRespected(t *testing.T) {
	// 对齐 Python data.get: 字段存在为 false 时不强制覆盖
	jsonStr := `{"scores":{"pedagogical":2,"appropriateness":2,"clarity":2,"engagement":2},"overall":2,"critique":"low","needs_regeneration":false}`
	result := parseCriticJson(jsonStr, "test-model", 10)
	if result == nil {
		t.Fatal("expected non-nil result")
	}
	if result.NeedsRegeneration {
		t.Error("explicit needs_regeneration=false must be respected")
	}
}

func TestParseCriticJson_WithMarkdown(t *testing.T) {
	jsonStr := "```json\n" + `{"scores":{"pedagogical":4.0,"appropriateness":4.0,"clarity":4.0,"engagement":4.0},"overall":4.0,"critique":"ok","needs_regeneration":false}` + "\n```"
	result := parseCriticJson(jsonStr, "test-model", 10)
	if result == nil {
		t.Fatal("expected non-nil result")
	}
	if result.Overall != 4.0 {
		t.Errorf("expected overall=4.0, got %f", result.Overall)
	}
}

func TestExtractJson(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{"plain", `{"a":1}`, `{"a":1}`},
		{"with markdown json", "```json\n{\"a\":1}\n```", `{"a":1}`},
		{"with markdown", "```\n{\"a\":1}\n```", `{"a":1}`},
		{"empty", "", ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := extractJson(tt.input)
			if result != tt.expected {
				t.Errorf("extractJson() = %q, want %q", result, tt.expected)
			}
		})
	}
}
