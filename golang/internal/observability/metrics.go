package observability

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Metrics Prometheus 风格指标
//
// 面试要点:
// - Counter: 单调递增 (请求总数)
// - Gauge: 可增可减 (活跃连接数)
// - Histogram: 分布统计 (请求延迟)
type Metrics struct {
	mu               sync.RWMutex
	requestCount     int64
	requestDuration  time.Duration
	activeConnections int64
	agentCalls       map[string]int64
	llmTokens        int64
}

// NewMetrics 创建指标收集器
func NewMetrics() *Metrics {
	return &Metrics{
		agentCalls: make(map[string]int64),
	}
}

// RecordRequest 记录请求
func (m *Metrics) RecordRequest(duration time.Duration) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.requestCount++
	m.requestDuration += duration
}

// RecordAgentCall 记录 Agent 调用
func (m *Metrics) RecordAgentCall(agentName string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.agentCalls[agentName]++
}

// RecordLLMTokens 记录 LLM token 使用
func (m *Metrics) RecordLLMTokens(tokens int64) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.llmTokens += tokens
}

// IncActiveConnections 增加活跃连接
func (m *Metrics) IncActiveConnections() {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.activeConnections++
}

// DecActiveConnections 减少活跃连接
func (m *Metrics) DecActiveConnections() {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.activeConnections--
}

// Snapshot 获取指标快照
func (m *Metrics) Snapshot() map[string]interface{} {
	m.mu.RLock()
	defer m.mu.RUnlock()

	agentCalls := make(map[string]int64)
	for k, v := range m.agentCalls {
		agentCalls[k] = v
	}

	return map[string]interface{}{
		"request_count":      m.requestCount,
		"request_duration_ms": m.requestDuration.Milliseconds(),
		"active_connections":  m.activeConnections,
		"agent_calls":         agentCalls,
		"llm_tokens_used":     m.llmTokens,
	}
}

// ServeHTTP 提供 /metrics 端点 (JSON 格式,向后兼容)
func (m *Metrics) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(m.Snapshot())
}

// ServePrometheus 提供 /metrics/prometheus 端点 (Prometheus text exposition format)
// 兼容 kube-prometheus-stack / ServiceMonitor 抓取
func (m *Metrics) ServePrometheus(w http.ResponseWriter, r *http.Request) {
	snapshot := m.Snapshot()
	var b strings.Builder

	// 帮助信息 + 指标
	b.WriteString("# HELP http_requests_total Total number of HTTP requests\n")
	b.WriteString("# TYPE http_requests_total counter\n")
	b.WriteString("http_requests_total " + strconv.FormatInt(snapshot["request_count"].(int64), 10) + "\n")

	b.WriteString("# HELP http_request_duration_ms Total request duration in milliseconds\n")
	b.WriteString("# TYPE http_request_duration_ms counter\n")
	b.WriteString("http_request_duration_ms " + strconv.FormatInt(snapshot["request_duration_ms"].(int64), 10) + "\n")

	b.WriteString("# HELP active_connections Current number of active connections\n")
	b.WriteString("# TYPE active_connections gauge\n")
	b.WriteString("active_connections " + strconv.FormatInt(snapshot["active_connections"].(int64), 10) + "\n")

	b.WriteString("# HELP llm_tokens_used_total Total LLM tokens consumed\n")
	b.WriteString("# TYPE llm_tokens_used_total counter\n")
	b.WriteString("llm_tokens_used_total " + strconv.FormatInt(snapshot["llm_tokens_used"].(int64), 10) + "\n")

	b.WriteString("# HELP agent_calls_total Total agent invocations by type\n")
	b.WriteString("# TYPE agent_calls_total counter\n")
	for agent, count := range snapshot["agent_calls"].(map[string]int64) {
		b.WriteString("agent_calls_total{agent=\"" + agent + "\"} " + strconv.FormatInt(count, 10) + "\n")
	}

	w.Header().Set("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
	w.Write([]byte(b.String()))
}
