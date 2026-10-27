package auth

import (
	"context"
	"net/http"
	"strings"
)

// contextKey context 键类型 (避免冲突)
type contextKey string

const userKey contextKey = "currentUser"

// AuthMiddleware HTTP 认证中间件
//
// 从 Authorization: Bearer <header> 提取 token
// 验证通过后注入 context.WithValue(ctx, userKey, &CurrentUser{...})
func AuthMiddleware(secret Key) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			tokenString := extractBearerToken(r)
			if tokenString == "" {
				http.Error(w, `{"error":"missing authorization token"}`, http.StatusUnauthorized)
				return
			}

			claims, err := ParseToken(secret, tokenString)
			if err != nil {
				http.Error(w, `{"error":"`+err.Error()+`"}`, http.StatusUnauthorized)
				return
			}

			// 仅允许 access token
			if claims.TokenType != "access" && claims.TokenType != "" {
				http.Error(w, `{"error":"invalid token type"}`, http.StatusUnauthorized)
				return
			}

			learnerID := claims.LearnerID
			if learnerID == "" {
				learnerID = claims.UserID // 兼容旧 token
			}
			user := &CurrentUser{
				ID:        claims.UserID,
				Email:     claims.Email,
				Role:      Role(claims.Role),
				TenantID:  claims.TenantID,
				LearnerID: learnerID,
			}

			ctx := context.WithValue(r.Context(), userKey, user)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// RequireRole 角色要求中间件 (需在 AuthMiddleware 之后)
func RequireRole(roles ...Role) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			user := GetUserFromContext(r.Context())
			if user == nil {
				http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
				return
			}
			if !HasRole(user, roles...) {
				http.Error(w, `{"error":"forbidden: insufficient role"}`, http.StatusForbidden)
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

// RequireMinRole 最低角色要求中间件
func RequireMinRole(minRole Role) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			user := GetUserFromContext(r.Context())
			if user == nil {
				http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
				return
			}
			if !HasMinRole(user, minRole) {
				http.Error(w, `{"error":"forbidden: insufficient role"}`, http.StatusForbidden)
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

// GetUserFromContext 从 context 获取当前用户
func GetUserFromContext(ctx context.Context) *CurrentUser {
	if user, ok := ctx.Value(userKey).(*CurrentUser); ok {
		return user
	}
	return nil
}

// WithUserContextForTest 注入用户到 context (仅用于测试)
func WithUserContextForTest(ctx context.Context, user *CurrentUser) context.Context {
	return context.WithValue(ctx, userKey, user)
}

// extractBearerToken 从请求头提取 Bearer token
func extractBearerToken(r *http.Request) string {
	authHeader := r.Header.Get("Authorization")
	if authHeader == "" {
		return ""
	}
	const prefix = "Bearer "
	if len(authHeader) > len(prefix) && strings.EqualFold(authHeader[:len(prefix)], prefix) {
		return strings.TrimSpace(authHeader[len(prefix):])
	}
	return ""
}
