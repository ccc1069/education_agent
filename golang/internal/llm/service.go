package llm

import (
	"context"
	"log"
	"sync"
	"sync/atomic"
	"time"
)

// LlmService LLM 统一入口 -- 对齐 Java LlmService
//
// 核心职责:
// - 熔断检查:连续失败达阈值则断开一段时间
// - 指数退避重试:默认 3 次(1s/2s/4s)
// - 超时异常不重试(避免拖死)
// - 记录指标(tokens + latency)
//
// 调用方应捕获错误并降级到启发式模板。
type LlmService struct {
	provider               LlmProvider
	maxRetries             int
	retryBackoff           time.Duration
	circuitBreakerThreshold int
	circuitBreakerDuration  time.Duration

	// 熔断状态
	consecutiveFailures atomic.Int32
	circuitOpenUntil    atomic.Value // time.Time
	mu                  sync.Mutex
}

// NewLlmService 创建 LlmService
func NewLlmService(provider LlmProvider) *LlmService {
	s := &LlmService{
		provider:               provider,
		maxRetries:             GetMaxRetries(),
		retryBackoff:           GetRetryBackoff(),
		circuitBreakerThreshold: GetCircuitBreakerThreshold(),
		circuitBreakerDuration:  GetCircuitBreakerDuration(),
	}
	return s
}

// NewLlmServiceWithConfig 使用指定配置创建(测试用)
func NewLlmServiceWithConfig(provider LlmProvider, maxRetries int, backoff time.Duration,
	cbThreshold int, cbDuration time.Duration) *LlmService {
	return &LlmService{
		provider:               provider,
		maxRetries:             maxRetries,
		retryBackoff:           backoff,
		circuitBreakerThreshold: cbThreshold,
		circuitBreakerDuration:  cbDuration,
	}
}

// Chat 同步调用 LLM,带重试与熔断
func (s *LlmService) Chat(ctx context.Context, req LlmRequest) (LlmResponse, error) {
	// 1. 熔断检查
	if s.isCircuitOpen() {
		return ErrorResponse("LLM 熔断器断开中"), errLlmUnavailable("熔断器断开", false)
	}

	var lastErr error

	for attempt := 1; attempt <= s.maxRetries; attempt++ {
		start := time.Now()
		resp, err := s.provider.Chat(ctx, req)
		latencyMs := float64(time.Since(start).Milliseconds())

		if err == nil {
			// 成功:重置失败计数
			s.consecutiveFailures.Store(0)
			log.Printf("[LlmService] LLM 调用成功: provider=%s model=%s tokens=%d latency=%.0fms",
				s.provider.Name(), resp.Model, resp.TotalTokens, latencyMs)
			return resp, nil
		}

		lastErr = err
		log.Printf("[LlmService] 第 %d/%d 次调用失败: %v", attempt, s.maxRetries, err)

		// 不可重试异常(网络超时),停止重试
		if unavailable, ok := err.(*LlmUnavailableError); ok && !unavailable.IsRetryable() {
			log.Printf("[LlmService] 不可重试异常,停止重试: %v", err)
			break
		}

		// 指数退避(最后一次不等待)
		if attempt < s.maxRetries {
			s.sleepBackoff(attempt)
		}
	}

	// 重试耗尽:触发熔断
	failures := s.consecutiveFailures.Add(1)
	if failures >= int32(s.circuitBreakerThreshold) {
		s.tripCircuitBreaker()
		log.Printf("[LlmService] 连续 %d 次失败,熔断器断开 %ds", failures, int(s.circuitBreakerDuration.Seconds()))
	}

	return ErrorResponse(lastErr.Error()), errLlmUnavailable(
		"LLM 调用失败(重试 "+itoa(s.maxRetries)+" 次): "+lastErr.Error(), false)
}

// ChatOrFallback 调用 LLM,失败返回 nil(调用方降级到启发式)
func (s *LlmService) ChatOrFallback(ctx context.Context, req LlmRequest) *LlmResponse {
	resp, err := s.Chat(ctx, req)
	if err != nil {
		log.Printf("[LlmService] LLM 不可用,调用方将降级: %v", err)
		return nil
	}
	return &resp
}

// ChatString 调用 LLM 返回内容字符串,失败返回空字符串
func (s *LlmService) ChatString(ctx context.Context, req LlmRequest) string {
	resp := s.ChatOrFallback(ctx, req)
	if resp == nil {
		return ""
	}
	return resp.Content
}

// GetProvider 返回当前 provider
func (s *LlmService) GetProvider() LlmProvider {
	return s.provider
}

// GetConsecutiveFailures 返回连续失败次数(测试用)
func (s *LlmService) GetConsecutiveFailures() int {
	return int(s.consecutiveFailures.Load())
}

// IsCircuitOpen 返回熔断器是否断开(测试用)
func (s *LlmService) IsCircuitOpen() bool {
	return s.isCircuitOpen()
}

// IsRealLlmEnabled 是否使用真实 LLM (供调用方判断是否需要降级)
func (s *LlmService) IsRealLlmEnabled() bool {
	return s.provider.IsAvailable()
}

// ==================== 熔断逻辑 ====================

func (s *LlmService) isCircuitOpen() bool {
	v := s.circuitOpenUntil.Load()
	if v == nil {
		return false
	}
	openUntil, ok := v.(time.Time)
	if !ok {
		return false
	}
	if time.Now().After(openUntil) {
		// 熔断到期,重置
		s.circuitOpenUntil.Store(time.Time{})
		s.consecutiveFailures.Store(0)
		log.Printf("[LlmService] 熔断器复位")
		return false
	}
	return true
}

func (s *LlmService) tripCircuitBreaker() {
	s.circuitOpenUntil.Store(time.Now().Add(s.circuitBreakerDuration))
}

// ==================== 重试逻辑 ====================

func (s *LlmService) sleepBackoff(attempt int) {
	delay := s.retryBackoff * time.Duration(1<<(attempt-1)) // 1s, 2s, 4s...
	time.Sleep(delay)
}

// itoa 整数转字符串(避免 strconv 导入)
func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}
