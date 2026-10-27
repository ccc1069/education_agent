package observability

import (
	"encoding/json"
	"net/http"
	"sync"
	"time"
)

// HealthCheck 健康检查函数
type HealthCheck func() error

// HealthStatus 健康状态
type HealthStatus struct {
	Status    string            `json:"status"`
	Checks    map[string]string `json:"checks"`
	Timestamp time.Time         `json:"timestamp"`
}

// HealthChecker 健康检查器
type HealthChecker struct {
	mu     sync.RWMutex
	checks map[string]HealthCheck
}

// NewHealthChecker 创建健康检查器
func NewHealthChecker() *HealthChecker {
	return &HealthChecker{
		checks: make(map[string]HealthCheck),
	}
}

// Register 注册健康检查
func (h *HealthChecker) Register(name string, check HealthCheck) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.checks[name] = check
}

// Check 执行所有健康检查
func (h *HealthChecker) Check() HealthStatus {
	h.mu.RLock()
	defer h.mu.RUnlock()

	status := HealthStatus{
		Status:    "healthy",
		Checks:    make(map[string]string),
		Timestamp: time.Now(),
	}

	for name, check := range h.checks {
		if err := check(); err != nil {
			status.Status = "unhealthy"
			status.Checks[name] = err.Error()
		} else {
			status.Checks[name] = "ok"
		}
	}

	return status
}

// ServeHTTP 提供 /health 端点
func (h *HealthChecker) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	status := h.Check()
	w.Header().Set("Content-Type", "application/json")
	if status.Status != "healthy" {
		w.WriteHeader(http.StatusServiceUnavailable)
	}
	json.NewEncoder(w).Encode(status)
}

// ReadyHandler 就绪检查
func (h *HealthChecker) ReadyHandler(w http.ResponseWriter, r *http.Request) {
	status := h.Check()
	w.Header().Set("Content-Type", "application/json")
	if status.Status != "healthy" {
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]string{"status": "not ready"})
		return
	}
	json.NewEncoder(w).Encode(map[string]string{"status": "ready"})
}

// LiveHandler 存活检查
func (h *HealthChecker) LiveHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "alive"})
}
