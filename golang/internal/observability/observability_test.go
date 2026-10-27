package observability

import (
	"bytes"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"
)

func TestLogger(t *testing.T) {
	var buf bytes.Buffer
	logger := NewLogger(InfoLevel, &buf)

	logger.Info("test message")

	output := buf.String()
	if !strings.Contains(output, "test message") {
		t.Errorf("log output should contain message, got: %s", output)
	}
	if !strings.Contains(output, `"level":"info"`) {
		t.Errorf("log output should contain level, got: %s", output)
	}
}

func TestLogger_WithField(t *testing.T) {
	var buf bytes.Buffer
	logger := NewLogger(InfoLevel, &buf)

	logger.WithField("user", "alice").WithField("action", "login").Info("user action")

	output := buf.String()
	if !strings.Contains(output, `"user":"alice"`) {
		t.Errorf("log should contain user field, got: %s", output)
	}
	if !strings.Contains(output, `"action":"login"`) {
		t.Errorf("log should contain action field, got: %s", output)
	}
}

func TestLogger_LevelFilter(t *testing.T) {
	var buf bytes.Buffer
	logger := NewLogger(ErrorLevel, &buf)

	logger.Debug("debug msg")
	logger.Info("info msg")
	logger.Error("error msg")

	output := buf.String()
	if strings.Contains(output, "debug msg") {
		t.Error("debug should be filtered")
	}
	if strings.Contains(output, "info msg") {
		t.Error("info should be filtered")
	}
	if !strings.Contains(output, "error msg") {
		t.Error("error should be present")
	}
}

func TestMetrics(t *testing.T) {
	metrics := NewMetrics()

	metrics.RecordRequest(100 * time.Millisecond)
	metrics.RecordRequest(200 * time.Millisecond)
	metrics.RecordAgentCall("tutor")
	metrics.RecordAgentCall("tutor")
	metrics.RecordAgentCall("assessment")
	metrics.RecordLLMTokens(500)

	metrics.IncActiveConnections()
	metrics.IncActiveConnections()
	metrics.DecActiveConnections()

	snapshot := metrics.Snapshot()

	if snapshot["request_count"] != int64(2) {
		t.Errorf("request_count: got %v, want 2", snapshot["request_count"])
	}
	if snapshot["active_connections"] != int64(1) {
		t.Errorf("active_connections: got %v, want 1", snapshot["active_connections"])
	}
	if snapshot["llm_tokens_used"] != int64(500) {
		t.Errorf("llm_tokens: got %v, want 500", snapshot["llm_tokens_used"])
	}

	agentCalls := snapshot["agent_calls"].(map[string]int64)
	if agentCalls["tutor"] != 2 {
		t.Errorf("tutor calls: got %d, want 2", agentCalls["tutor"])
	}
}

func TestMetrics_ServeHTTP(t *testing.T) {
	metrics := NewMetrics()
	metrics.RecordRequest(time.Millisecond)

	// 测试 JSON 序列化
	snapshot := metrics.Snapshot()
	data, err := json.Marshal(snapshot)
	if err != nil {
		t.Fatalf("Marshal failed: %v", err)
	}
	if !strings.Contains(string(data), "request_count") {
		t.Error("JSON should contain request_count")
	}
}

func TestHealthChecker(t *testing.T) {
	checker := NewHealthChecker()

	// 注册健康检查
	checker.Register("database", func() error { return nil })
	checker.Register("cache", func() error { return nil })

	status := checker.Check()
	if status.Status != "healthy" {
		t.Errorf("status: got %s, want healthy", status.Status)
	}
	if len(status.Checks) != 2 {
		t.Errorf("checks: got %d, want 2", len(status.Checks))
	}
}

func TestHealthChecker_Unhealthy(t *testing.T) {
	checker := NewHealthChecker()

	checker.Register("database", func() error { return nil })
	checker.Register("cache", func() error { return errors.New("connection failed") })

	status := checker.Check()
	if status.Status != "unhealthy" {
		t.Errorf("status: got %s, want unhealthy", status.Status)
	}
}

func TestHealthChecker_LiveHandler(t *testing.T) {
	checker := NewHealthChecker()

	// 存活检查应始终返回 alive
	status := checker.Check()
	if status.Timestamp.IsZero() {
		t.Error("timestamp should be set")
	}
}
