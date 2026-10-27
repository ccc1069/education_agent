package llm

import (
	"log"
	"os"
	"strconv"
	"strings"
	"time"
)

// LlmProviderFactory LLM Provider 工厂 -- 对齐 Java LlmProviderFactory
//
// 配置项 APP_LLM_PROVIDER:
// - auto(默认):有 OpenAI key 用 OpenAI,否则用 Mock
// - openai:强制使用 OpenAI
// - mock:强制使用 Mock
type LlmProviderFactory struct {
	openAiProvider *OpenAiLlmProvider
	mockProvider   *MockLlmProvider
	configuredProvider string
}

// NewLlmProviderFactory 从环境变量创建工厂
func NewLlmProviderFactory() *LlmProviderFactory {
	provider := strings.ToLower(strings.TrimSpace(getEnv("APP_LLM_PROVIDER", "auto")))
	if provider == "" {
		provider = "auto"
	}

	apiKey := getEnv("APP_LLM_API_KEY", "")
	baseURL := getEnv("APP_LLM_BASE_URL", "https://api.openai.com/v1")
	model := getEnv("APP_LLM_MODEL", "gpt-4o-mini")
	timeoutSec := getEnvInt("APP_LLM_TIMEOUT", 30)

	return &LlmProviderFactory{
		openAiProvider:     NewOpenAiLlmProvider(apiKey, baseURL, model, timeoutSec),
		mockProvider:       NewMockLlmProvider(),
		configuredProvider: provider,
	}
}

// NewLlmProviderFactoryWithProviders 使用指定 provider 创建工厂(测试用)
func NewLlmProviderFactoryWithProviders(openAi *OpenAiLlmProvider, mock *MockLlmProvider, configured string) *LlmProviderFactory {
	return &LlmProviderFactory{
		openAiProvider:     openAi,
		mockProvider:       mock,
		configuredProvider: configured,
	}
}

// GetProvider 获取按配置选择的 provider
func (f *LlmProviderFactory) GetProvider() LlmProvider {
	switch f.configuredProvider {
	case "openai":
		log.Printf("[LlmProviderFactory] 使用 OpenAI provider")
		return f.openAiProvider
	case "mock":
		log.Printf("[LlmProviderFactory] 使用 Mock provider")
		return f.mockProvider
	default:
		// auto:优先 OpenAI(有 key 时)
		if f.openAiProvider.IsAvailable() {
			log.Printf("[LlmProviderFactory] auto 模式:OpenAI key 已配置,使用 OpenAI provider")
			return f.openAiProvider
		}
		log.Printf("[LlmProviderFactory] auto 模式:无 OpenAI key,降级到 Mock provider")
		return f.mockProvider
	}
}

// IsRealLlmEnabled 是否使用真实 LLM(供调用方判断是否需要降级逻辑)
func (f *LlmProviderFactory) IsRealLlmEnabled() bool {
	if f.configuredProvider == "mock" {
		return false
	}
	return f.openAiProvider.IsAvailable()
}

// NewLlmProviderFromEnv 从环境变量创建 LlmProvider (便捷函数)
func NewLlmProviderFromEnv() LlmProvider {
	return NewLlmProviderFactory().GetProvider()
}

// GetMaxTokens 从环境变量获取 max tokens
func GetMaxTokens() int {
	return getEnvInt("APP_LLM_MAX_TOKENS", 1024)
}

// GetTemperature 从环境变量获取 temperature
func GetTemperature() float64 {
	return getEnvFloat("APP_LLM_TEMPERATURE", 0.7)
}

// GetMaxRetries 从环境变量获取最大重试次数
func GetMaxRetries() int {
	return getEnvInt("APP_LLM_MAX_RETRIES", 3)
}

// GetRetryBackoff 从环境变量获取重试退避时间
func GetRetryBackoff() time.Duration {
	return time.Duration(getEnvInt("APP_LLM_RETRY_BACKOFF_MS", 1000)) * time.Millisecond
}

// GetCircuitBreakerThreshold 从环境变量获取熔断阈值
func GetCircuitBreakerThreshold() int {
	return getEnvInt("APP_LLM_CB_THRESHOLD", 5)
}

// GetCircuitBreakerDuration 从环境变量获取熔断持续时间
func GetCircuitBreakerDuration() time.Duration {
	return time.Duration(getEnvInt("APP_LLM_CB_DURATION_SEC", 60)) * time.Second
}

// GetDebateRounds 从环境变量获取辩论轮次
func GetDebateRounds() int {
	return getEnvInt("APP_LLM_DEBATE_ROUNDS", 2)
}

// getEnv 获取环境变量
func getEnv(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}

// getEnvInt 获取整数环境变量
func getEnvInt(key string, defaultVal int) int {
	if val := os.Getenv(key); val != "" {
		if i, err := strconv.Atoi(val); err == nil {
			return i
		}
	}
	return defaultVal
}

// getEnvFloat 获取浮点环境变量
func getEnvFloat(key string, defaultVal float64) float64 {
	if val := os.Getenv(key); val != "" {
		if f, err := strconv.ParseFloat(val, 64); err == nil {
			return f
		}
	}
	return defaultVal
}
