package tenant

import (
	"context"
	"net/http"

	"multi-agent-education/golang/internal/auth"
)

// TenantMiddleware 多租户中间件
//
// 从 X-Tenant-ID header 读取租户 ID → context
// 非 admin 强制 tenantID = user's tenantID (防伪造)
//
// 面试要点:
// - admin 可以跨租户访问 (指定任意 X-Tenant-ID)
// - 普通用户只能访问自己租户的数据
func TenantMiddleware() func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			tenantID := r.Header.Get("X-Tenant-ID")

			// 如果已认证,检查租户一致性
			user := auth.GetUserFromContext(r.Context())
			if user != nil && !auth.IsAdmin(user) {
				// 非 admin 强制使用自己的 tenantID
				tenantID = user.TenantID
			}

			ctx := WithTenantID(r.Context(), tenantID)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// TenantScopedHandler 租户作用域处理辅助函数
//
// 检查请求的 tenantID 是否与用户匹配 (用于资源级权限)
func AuthorizeTenantAccess(r *http.Request) bool {
	user := auth.GetUserFromContext(r.Context())
	if user == nil {
		return false
	}
	// admin 可以访问所有租户
	if auth.IsAdmin(user) {
		return true
	}
	requestTenantID := MustGetTenantID(r.Context())
	return user.TenantID == requestTenantID
}

// EnsureTenantContext 确保 context 中有 tenantID (用于测试/内部调用)
func EnsureTenantContext(ctx context.Context, defaultTenantID string) context.Context {
	if tenantID, ok := GetTenantID(ctx); ok && tenantID != "" {
		return ctx
	}
	return WithTenantID(ctx, defaultTenantID)
}
