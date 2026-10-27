package tenant

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"multi-agent-education/golang/internal/auth"
)

func TestWithAndGetTenantID(t *testing.T) {
	ctx := context.Background()

	// 初始为空
	if _, ok := GetTenantID(ctx); ok {
		t.Error("should not have tenantID initially")
	}

	// 注入后
	ctx = WithTenantID(ctx, "tenant-001")
	tenantID, ok := GetTenantID(ctx)
	if !ok {
		t.Error("should have tenantID after WithTenantID")
	}
	if tenantID != "tenant-001" {
		t.Errorf("got %s, want tenant-001", tenantID)
	}
}

func TestMustGetTenantID(t *testing.T) {
	ctx := context.Background()
	if MustGetTenantID(ctx) != "" {
		t.Error("should return empty for missing tenant")
	}

	ctx = WithTenantID(ctx, "tenant-002")
	if MustGetTenantID(ctx) != "tenant-002" {
		t.Errorf("got %s, want tenant-002", MustGetTenantID(ctx))
	}
}

func TestTenantMiddleware(t *testing.T) {
	handler := TenantMiddleware()(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		tenantID := MustGetTenantID(r.Context())
		w.Write([]byte(tenantID))
	}))

	// 测试 1: 无认证,使用 header
	req := httptest.NewRequest("GET", "/", nil)
	req.Header.Set("X-Tenant-ID", "tenant-from-header")
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Body.String() != "tenant-from-header" {
		t.Errorf("got %s, want tenant-from-header", rr.Body.String())
	}
}

func TestTenantMiddleware_NonAdminForced(t *testing.T) {
	secret := auth.Key([]byte("test-secret-key-for-unit-tests-32bytes!"))

	handler := auth.AuthMiddleware(secret)(
		TenantMiddleware()(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			tenantID := MustGetTenantID(r.Context())
			w.Write([]byte(tenantID))
		})),
	)

	// student 尝试伪造 X-Tenant-ID,应被强制改为自己的 tenantID
	token, _ := auth.CreateAccessToken(secret, "user-001", "test@example.com", "student", "tenant-student", "user-001")
	req := httptest.NewRequest("GET", "/", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("X-Tenant-ID", "tenant-fake")
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Body.String() != "tenant-student" {
		t.Errorf("non-admin should be forced to own tenant, got %s", rr.Body.String())
	}
}

func TestTenantMiddleware_AdminCanSpecify(t *testing.T) {
	secret := auth.Key([]byte("test-secret-key-for-unit-tests-32bytes!"))

	handler := auth.AuthMiddleware(secret)(
		TenantMiddleware()(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			tenantID := MustGetTenantID(r.Context())
			w.Write([]byte(tenantID))
		})),
	)

	// admin 可以指定任意 X-Tenant-ID
	token, _ := auth.CreateAccessToken(secret, "admin-001", "admin@example.com", "admin", "tenant-admin", "admin-001")
	req := httptest.NewRequest("GET", "/", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("X-Tenant-ID", "tenant-any")
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Body.String() != "tenant-any" {
		t.Errorf("admin should specify any tenant, got %s", rr.Body.String())
	}
}

func TestAuthorizeTenantAccess(t *testing.T) {
	secret := auth.Key([]byte("test-secret-key-for-unit-tests-32bytes!"))

	// student 访问自己的租户
	studentToken, _ := auth.CreateAccessToken(secret, "user-001", "test@example.com", "student", "tenant-001", "user-001")
	req := httptest.NewRequest("GET", "/", nil)
	req.Header.Set("Authorization", "Bearer "+studentToken)
	req.Header.Set("X-Tenant-ID", "tenant-001")
	ctx := auth.WithUserContextForTest(req.Context(), &auth.CurrentUser{
		ID:       "user-001",
		Role:     auth.RoleStudent,
		TenantID: "tenant-001",
	})
	req = req.WithContext(WithTenantID(ctx, "tenant-001"))
	if !AuthorizeTenantAccess(req) {
		t.Error("student should access own tenant")
	}

	// student 访问其他租户
	req2 := httptest.NewRequest("GET", "/", nil)
	req2.Header.Set("Authorization", "Bearer "+studentToken)
	ctx2 := auth.WithUserContextForTest(req2.Context(), &auth.CurrentUser{
		ID:       "user-001",
		Role:     auth.RoleStudent,
		TenantID: "tenant-001",
	})
	req2 = req2.WithContext(WithTenantID(ctx2, "tenant-002"))
	if AuthorizeTenantAccess(req2) {
		t.Error("student should not access other tenant")
	}
}

func TestEnsureTenantContext(t *testing.T) {
	ctx := context.Background()
	ctx = EnsureTenantContext(ctx, "default-tenant")
	if MustGetTenantID(ctx) != "default-tenant" {
		t.Errorf("got %s, want default-tenant", MustGetTenantID(ctx))
	}

	// 已有 tenantID 时不覆盖
	ctx = WithTenantID(ctx, "existing-tenant")
	ctx = EnsureTenantContext(ctx, "default-tenant")
	if MustGetTenantID(ctx) != "existing-tenant" {
		t.Errorf("should not override existing tenant, got %s", MustGetTenantID(ctx))
	}
}
