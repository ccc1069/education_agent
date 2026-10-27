package tenant

import "context"

// tenantKey context 键类型
type tenantKey struct{}

// WithTenantID 将 tenantID 注入 context
//
// 面试要点:
// - 使用自定义类型作为 key,避免 string key 冲突
// - TenantID 贯穿请求生命周期,实现数据隔离
func WithTenantID(ctx context.Context, tenantID string) context.Context {
	return context.WithValue(ctx, tenantKey{}, tenantID)
}

// GetTenantID 从 context 获取 tenantID
func GetTenantID(ctx context.Context) (string, bool) {
	tenantID, ok := ctx.Value(tenantKey{}).(string)
	return tenantID, ok
}

// MustGetTenantID 获取 tenantID,不存在则返回空字符串
func MustGetTenantID(ctx context.Context) string {
	tenantID, _ := GetTenantID(ctx)
	return tenantID
}
