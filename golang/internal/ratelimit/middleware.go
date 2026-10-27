package ratelimit

import (
	"net"
	"net/http"
	"strconv"
	"time"

	"multi-agent-education/golang/internal/auth"
)

// RateLimitMiddleware 限流中间件
//
// Key 策略:
// - 已认证用户: user_id
// - 匿名用户: IP 地址
//
// 响应头:
// - X-RateLimit-Limit: 总配额
// - X-RateLimit-Remaining: 剩余配额
// - X-RateLimit-Reset: 重置时间 (unix seconds)
// - Retry-After: 被限流时返回
func RateLimitMiddleware(limiter *SlidingWindowLimiter) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			key := getRateLimitKey(r)

			allowed, remaining, resetAt := limiter.Allow(key)

			// 设置响应头
			w.Header().Set("X-RateLimit-Limit", strconv.Itoa(limiter.limit))
			w.Header().Set("X-RateLimit-Remaining", strconv.Itoa(remaining))
			w.Header().Set("X-RateLimit-Reset", strconv.FormatInt(resetAt.Unix(), 10))

			if !allowed {
				w.Header().Set("Retry-After", strconv.Itoa(int(time.Until(resetAt).Seconds())+1))
				http.Error(w, `{"error":"rate limit exceeded"}`, http.StatusTooManyRequests)
				return
			}

			next.ServeHTTP(w, r)
		})
	}
}

// getRateLimitKey 获取限流 key
func getRateLimitKey(r *http.Request) string {
	// 已认证用户使用 user_id
	if user := auth.GetUserFromContext(r.Context()); user != nil {
		return "user:" + user.ID
	}
	// 匿名用户使用 IP
	return "ip:" + getClientIP(r)
}

// getClientIP 获取客户端真实 IP
func getClientIP(r *http.Request) string {
	// 优先 X-Forwarded-For
	xff := r.Header.Get("X-Forwarded-For")
	if xff != "" {
		return xff
	}
	xri := r.Header.Get("X-Real-Ip")
	if xri != "" {
		return xri
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}
