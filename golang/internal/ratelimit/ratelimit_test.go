package ratelimit

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestSlidingWindowLimiter_Allow(t *testing.T) {
	limiter := NewSlidingWindowLimiter(3, time.Second)

	// 前 3 次应允许
	for i := 0; i < 3; i++ {
		allowed, _, _ := limiter.Allow("key1")
		if !allowed {
			t.Errorf("request %d should be allowed", i+1)
		}
	}

	// 第 4 次应拒绝
	allowed, remaining, _ := limiter.Allow("key1")
	if allowed {
		t.Error("4th request should be denied")
	}
	if remaining != 0 {
		t.Errorf("remaining should be 0, got %d", remaining)
	}
}

func TestSlidingWindowLimiter_WindowReset(t *testing.T) {
	limiter := NewSlidingWindowLimiter(2, 200*time.Millisecond)

	// 用完配额
	limiter.Allow("key1")
	limiter.Allow("key1")

	// 应拒绝
	allowed, _, _ := limiter.Allow("key1")
	if allowed {
		t.Error("should be denied")
	}

	// 等待窗口过期
	time.Sleep(250 * time.Millisecond)

	// 应再次允许
	allowed, _, _ = limiter.Allow("key1")
	if !allowed {
		t.Error("should be allowed after window reset")
	}
}

func TestSlidingWindowLimiter_DifferentKeys(t *testing.T) {
	limiter := NewSlidingWindowLimiter(1, time.Second)

	// key1 用尽
	allowed, _, _ := limiter.Allow("key1")
	if !allowed {
		t.Error("key1 first request should be allowed")
	}
	allowed, _, _ = limiter.Allow("key1")
	if allowed {
		t.Error("key1 second request should be denied")
	}

	// key2 不受影响
	allowed, _, _ = limiter.Allow("key2")
	if !allowed {
		t.Error("key2 should be allowed independently")
	}
}

func TestSlidingWindowLimiter_AllowN(t *testing.T) {
	limiter := NewSlidingWindowLimiter(5, time.Second)

	allowed, remaining, _ := limiter.AllowN("key1", 3)
	if !allowed {
		t.Error("should allow 3 requests")
	}
	if remaining != 2 {
		t.Errorf("remaining should be 2, got %d", remaining)
	}

	// 再请求 3 个 (超过剩余)
	allowed, _, _ = limiter.AllowN("key1", 3)
	if allowed {
		t.Error("should deny, only 2 remaining")
	}
}

func TestSlidingWindowLimiter_Remaining(t *testing.T) {
	limiter := NewSlidingWindowLimiter(5, time.Second)

	if limiter.Remaining("key1") != 5 {
		t.Error("initial remaining should be 5")
	}

	limiter.Allow("key1")
	if limiter.Remaining("key1") != 4 {
		t.Errorf("remaining should be 4, got %d", limiter.Remaining("key1"))
	}
}

func TestSlidingWindowLimiter_Reset(t *testing.T) {
	limiter := NewSlidingWindowLimiter(1, time.Second)

	limiter.Allow("key1")
	allowed, _, _ := limiter.Allow("key1")
	if allowed {
		t.Error("should be denied")
	}

	limiter.Reset("key1")
	allowed, _, _ = limiter.Allow("key1")
	if !allowed {
		t.Error("should be allowed after reset")
	}
}

func TestRateLimitMiddleware(t *testing.T) {
	limiter := NewSlidingWindowLimiter(2, time.Second)
	handler := RateLimitMiddleware(limiter)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))

	// 前 2 次应通过
	for i := 0; i < 2; i++ {
		req := httptest.NewRequest("GET", "/", nil)
		req.RemoteAddr = "127.0.0.1:12345"
		rr := httptest.NewRecorder()
		handler.ServeHTTP(rr, req)
		if rr.Code != http.StatusOK {
			t.Errorf("request %d: got %d, want 200", i+1, rr.Code)
		}
	}

	// 第 3 次应限流
	req := httptest.NewRequest("GET", "/", nil)
	req.RemoteAddr = "127.0.0.1:12345"
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusTooManyRequests {
		t.Errorf("rate limited: got %d, want 429", rr.Code)
	}

	// 验证响应头
	if rr.Header().Get("X-RateLimit-Limit") != "2" {
		t.Error("X-RateLimit-Limit header missing")
	}
	if rr.Header().Get("Retry-After") == "" {
		t.Error("Retry-After header missing on rate limit")
	}
}

func TestGetClientIP(t *testing.T) {
	// X-Forwarded-For
	req := httptest.NewRequest("GET", "/", nil)
	req.Header.Set("X-Forwarded-For", "1.2.3.4")
	if got := getClientIP(req); got != "1.2.3.4" {
		t.Errorf("got %s, want 1.2.3.4", got)
	}

	// X-Real-Ip
	req = httptest.NewRequest("GET", "/", nil)
	req.Header.Set("X-Real-Ip", "5.6.7.8")
	if got := getClientIP(req); got != "5.6.7.8" {
		t.Errorf("got %s, want 5.6.7.8", got)
	}

	// RemoteAddr
	req = httptest.NewRequest("GET", "/", nil)
	req.RemoteAddr = "9.10.11.12:12345"
	if got := getClientIP(req); got != "9.10.11.12" {
		t.Errorf("got %s, want 9.10.11.12", got)
	}
}
