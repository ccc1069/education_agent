package ratelimit

import (
	"sync"
	"time"
)

// SlidingWindowLimiter 滑动窗口限流器
//
// 面试要点:
// - 滑动窗口比固定窗口更精确,避免窗口边界突发
// - 使用 map[key][]timestamp 记录请求时间 (毫秒精度)
// - 清理过期时间戳,控制内存
type SlidingWindowLimiter struct {
	mu      sync.Mutex
	windows map[string][]int64 // key -> timestamps (unix milliseconds)
	limit   int                // 窗口内最大请求数
	window  time.Duration      // 窗口大小
}

// NewSlidingWindowLimiter 创建滑动窗口限流器
func NewSlidingWindowLimiter(limit int, window time.Duration) *SlidingWindowLimiter {
	return &SlidingWindowLimiter{
		windows: make(map[string][]int64),
		limit:   limit,
		window:  window,
	}
}

// Allow 检查是否允许请求
//
// 返回 (allowed, remaining, resetAt)
func (l *SlidingWindowLimiter) Allow(key string) (allowed bool, remaining int, resetAt time.Time) {
	return l.AllowN(key, 1)
}

// AllowN 检查是否允许 N 个请求
func (l *SlidingWindowLimiter) AllowN(key string, n int) (allowed bool, remaining int, resetAt time.Time) {
	l.mu.Lock()
	defer l.mu.Unlock()

	nowMs := time.Now().UnixMilli()
	windowStart := time.Now().Add(-l.window).UnixMilli()

	// 清理过期时间戳
	timestamps := l.windows[key]
	valid := make([]int64, 0, len(timestamps)+1)
	for _, ts := range timestamps {
		if ts > windowStart {
			valid = append(valid, ts)
		}
	}

	// 检查是否超限
	if len(valid)+n > l.limit {
		// 计算 resetAt (最早有效时间戳 + 窗口)
		if len(valid) > 0 {
			resetAt = time.UnixMilli(valid[0]).Add(l.window)
		} else {
			resetAt = time.Now().Add(l.window)
		}
		l.windows[key] = valid
		return false, 0, resetAt
	}

	// 添加当前请求时间戳
	for i := 0; i < n; i++ {
		valid = append(valid, nowMs)
	}
	l.windows[key] = valid

	remaining = l.limit - len(valid)
	resetAt = time.Now().Add(l.window)
	return true, remaining, resetAt
}

// Remaining 获取剩余配额
func (l *SlidingWindowLimiter) Remaining(key string) int {
	l.mu.Lock()
	defer l.mu.Unlock()

	windowStart := time.Now().Add(-l.window).UnixMilli()

	timestamps := l.windows[key]
	valid := 0
	for _, ts := range timestamps {
		if ts > windowStart {
			valid++
		}
	}
	remaining := l.limit - valid
	if remaining < 0 {
		return 0
	}
	return remaining
}

// Reset 重置某个 key 的限流
func (l *SlidingWindowLimiter) Reset(key string) {
	l.mu.Lock()
	defer l.mu.Unlock()
	delete(l.windows, key)
}
