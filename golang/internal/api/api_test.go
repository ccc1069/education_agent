package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"multi-agent-education/golang/internal/agent"
	"multi-agent-education/golang/internal/audit"
	"multi-agent-education/golang/internal/auth"
	"multi-agent-education/golang/internal/eventbus"
	"multi-agent-education/golang/internal/llm"
	"multi-agent-education/golang/internal/notification"
	"multi-agent-education/golang/internal/observability"
	"multi-agent-education/golang/internal/privacy"
	"multi-agent-education/golang/internal/question"
	"multi-agent-education/golang/internal/rag"
	"multi-agent-education/golang/internal/scheduler"
	"multi-agent-education/golang/internal/teacher"
	"multi-agent-education/golang/internal/tenant"
	"multi-agent-education/golang/internal/vision"
)

// newTestRouter 创建测试用 Router (已认证)
func newTestRouter() (*Router, *auth.UserStore) {
	bus := eventbus.New()
	secret := auth.Key([]byte("test-secret-32bytes-for-test-only!"))
	llmSvc := llm.NewLlmService(llm.NewMockLlmProvider())

	assessmentAgent := agent.NewAssessmentAgent(bus)
	ragService := rag.NewRAGService(rag.NewMockEmbeddingProvider(), rag.NewInMemoryVectorStore())
	questionBank := question.NewQuestionBank()
	classService := teacher.NewClassService()
	assignmentService := teacher.NewAssignmentService()
	dashboardService := teacher.NewDashboardService(classService, assignmentService)
	metrics := observability.NewMetrics()
	healthChecker := observability.NewHealthChecker()
	userStore := auth.NewUserStore()
	refreshStore := auth.NewRefreshTokenStore()
	privacyService := privacy.NewPrivacyService()
	auditService := audit.NewAuditService([]byte(secret))
	taskQueue := scheduler.NewTaskQueue(2, 10)
	notificationSvc := notification.NewNotificationService()
	tenantService := tenant.NewTenantService()
	wsManager := NewWebSocketManager(bus, secret)
	visionService := vision.NewVisionService(llmSvc)

	r := NewRouter(
		bus, assessmentAgent, secret, llmSvc,
		ragService, questionBank, classService, assignmentService,
		dashboardService, metrics, healthChecker,
		userStore, refreshStore, privacyService, auditService, taskQueue,
		notificationSvc, tenantService, wsManager, visionService, nil,
	)
	return r, userStore
}

// extractBearer 从响应中提取 token (简化测试)
func extractToken(t *testing.T, body string) string {
	var resp map[string]interface{}
	if err := json.Unmarshal([]byte(body), &resp); err != nil {
		t.Fatalf("unmarshal response failed: %v", err)
	}
	token, ok := resp["access_token"].(string)
	if !ok || token == "" {
		t.Fatalf("no access_token in response: %s", body)
	}
	return token
}

// TestHealthEndpoint 测试健康检查
func TestHealthEndpoint(t *testing.T) {
	r, _ := newTestRouter()
	handler := r.Setup()

	req := httptest.NewRequest("GET", "/api/v1/health", nil)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["status"] != "ok" {
		t.Fatalf("expected status=ok, got %v", resp["status"])
	}
}

// TestRegisterEndpoint 测试注册
func TestRegisterEndpoint(t *testing.T) {
	r, _ := newTestRouter()
	handler := r.Setup()

	body := `{"email":"test@example.com","password":"pass123","role":"student"}`
	req := httptest.NewRequest("POST", "/api/v1/auth/register", strings.NewReader(body))
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["user_id"] == nil {
		t.Fatal("expected user_id in response")
	}
	if resp["learner_id"] == nil {
		t.Fatal("expected learner_id in response")
	}
	if resp["message"] == nil {
		t.Fatal("expected message in response")
	}
}

// TestLoginEndpoint 测试登录
func TestLoginEndpoint(t *testing.T) {
	r, userStore := newTestRouter()
	handler := r.Setup()

	// 先创建用户
	hash, _ := auth.HashPassword("pass123")
	userStore.CreateUser("login@test.com", hash, auth.RoleStudent, "default")

	body := `{"email":"login@test.com","password":"pass123"}`
	req := httptest.NewRequest("POST", "/api/v1/auth/login", strings.NewReader(body))
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["access_token"] == nil {
		t.Fatal("expected access_token")
	}
	if resp["refresh_token"] == nil {
		t.Fatal("expected refresh_token")
	}
}

// TestRefreshEndpoint 测试刷新 token
func TestRefreshEndpoint(t *testing.T) {
	r, userStore := newTestRouter()
	handler := r.Setup()

	// 先创建用户并登录
	hash, _ := auth.HashPassword("pass123")
	user, _ := userStore.CreateUser("refresh@test.com", hash, auth.RoleStudent, "default")

	refreshToken, _ := r.refreshStore.Create(user.ID, auth.DefaultRefreshDuration)

	body := `{"refresh_token":"` + refreshToken + `"}`
	req := httptest.NewRequest("POST", "/api/v1/auth/refresh", strings.NewReader(body))
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["access_token"] == nil {
		t.Fatal("expected new access_token")
	}
	if resp["refresh_token"] == nil {
		t.Fatal("expected new refresh_token")
	}
}

// TestLogoutEndpoint 测试登出
func TestLogoutEndpoint(t *testing.T) {
	r, _ := newTestRouter()
	handler := r.Setup()

	body := `{"refresh_token":"some-token"}`
	req := httptest.NewRequest("POST", "/api/v1/auth/logout", strings.NewReader(body))
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["status"] != "logged_out" {
		t.Fatalf("expected status=logged_out, got %v", resp["status"])
	}
}

// TestMeEndpoint 测试当前用户信息
func TestMeEndpoint(t *testing.T) {
	r, userStore := newTestRouter()
	handler := r.Setup()

	// 创建用户并生成 token
	hash, _ := auth.HashPassword("pass123")
	user, _ := userStore.CreateUser("me@test.com", hash, auth.RoleStudent, "default")
	token, _ := auth.CreateAccessToken(r.jwtSecret, user.ID, user.Email, string(user.Role), user.TenantID, user.LearnerID)

	req := httptest.NewRequest("GET", "/api/v1/auth/me", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["email"] != "me@test.com" {
		t.Fatalf("expected email=me@test.com, got %v", resp["email"])
	}
	if resp["learner_id"] == nil || resp["learner_id"] == "" {
		t.Fatal("expected learner_id in /auth/me")
	}
}

// TestPrivacyConsentEndpoint 测试隐私同意
func TestPrivacyConsentEndpoint(t *testing.T) {
	r, userStore := newTestRouter()
	handler := r.Setup()

	hash, _ := auth.HashPassword("pass123")
	user, _ := userStore.CreateUser("privacy@test.com", hash, auth.RoleStudent, "default")
	token, _ := auth.CreateAccessToken(r.jwtSecret, user.ID, user.Email, string(user.Role), user.TenantID, user.LearnerID)

	// 设置同意
	body := `{"consent_type":"analytics","granted":true}`
	req := httptest.NewRequest("POST", "/api/v1/privacy/consent", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+token)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}

	// 获取同意状态
	req = httptest.NewRequest("GET", "/api/v1/privacy/consent?type=analytics", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	w = httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["granted"] != true {
		t.Fatalf("expected granted=true, got %v", resp["granted"])
	}
}

// TestNotificationEndpoint 测试通知列表
func TestNotificationEndpoint(t *testing.T) {
	r, userStore := newTestRouter()
	handler := r.Setup()

	hash, _ := auth.HashPassword("pass123")
	user, _ := userStore.CreateUser("notif@test.com", hash, auth.RoleStudent, "default")
	token, _ := auth.CreateAccessToken(r.jwtSecret, user.ID, user.Email, string(user.Role), user.TenantID, user.LearnerID)

	req := httptest.NewRequest("GET", "/api/v1/notifications", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["notifications"] == nil {
		t.Fatal("expected notifications field")
	}
}

// TestTenantEndpoint 测试租户管理
func TestTenantEndpoint(t *testing.T) {
	r, userStore := newTestRouter()
	handler := r.Setup()

	// 创建 admin 用户
	hash, _ := auth.HashPassword("pass123")
	admin, _ := userStore.CreateUser("admin@test.com", hash, auth.RoleAdmin, "default")
	adminToken, _ := auth.CreateAccessToken(r.jwtSecret, admin.ID, admin.Email, string(admin.Role), admin.TenantID, admin.LearnerID)

	// 创建租户
	body := `{"name":"Test School","slug":"test-school","plan":"pro"}`
	req := httptest.NewRequest("POST", "/api/v1/tenants", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+adminToken)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	tenantData, ok := resp["tenant"].(map[string]interface{})
	if !ok {
		t.Fatal("expected tenant object")
	}
	if tenantData["name"] != "Test School" {
		t.Fatalf("expected name=Test School, got %v", tenantData["name"])
	}

	// 列出租户
	req = httptest.NewRequest("GET", "/api/v1/tenants", nil)
	req.Header.Set("Authorization", "Bearer "+adminToken)
	w = httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}
}

// TestAuditEndpoint 测试审计日志
func TestAuditEndpoint(t *testing.T) {
	r, userStore := newTestRouter()
	handler := r.Setup()

	hash, _ := auth.HashPassword("pass123")
	admin, _ := userStore.CreateUser("admin-audit@test.com", hash, auth.RoleAdmin, "default")
	adminToken, _ := auth.CreateAccessToken(r.jwtSecret, admin.ID, admin.Email, string(admin.Role), admin.TenantID, admin.LearnerID)

	req := httptest.NewRequest("GET", "/api/v1/audit/logs", nil)
	req.Header.Set("Authorization", "Bearer "+adminToken)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["logs"] == nil {
		t.Fatal("expected logs field")
	}
}

// TestTaskEndpoint 测试任务列表
func TestTaskEndpoint(t *testing.T) {
	r, userStore := newTestRouter()
	handler := r.Setup()

	hash, _ := auth.HashPassword("pass123")
	admin, _ := userStore.CreateUser("admin-task@test.com", hash, auth.RoleAdmin, "default")
	adminToken, _ := auth.CreateAccessToken(r.jwtSecret, admin.ID, admin.Email, string(admin.Role), admin.TenantID, admin.LearnerID)

	req := httptest.NewRequest("GET", "/api/v1/admin/tasks", nil)
	req.Header.Set("Authorization", "Bearer "+adminToken)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["tasks"] == nil {
		t.Fatal("expected tasks field")
	}
	if resp["stats"] == nil {
		t.Fatal("expected stats field")
	}
}

// TestLearnerProgressEndpoint 测试学习进度
func TestLearnerProgressEndpoint(t *testing.T) {
	r, userStore := newTestRouter()
	handler := r.Setup()

	hash, _ := auth.HashPassword("pass123")
	user, _ := userStore.CreateUser("learner@test.com", hash, auth.RoleStudent, "default")
	token, _ := auth.CreateAccessToken(r.jwtSecret, user.ID, user.Email, string(user.Role), user.TenantID, user.LearnerID)

	req := httptest.NewRequest("GET", "/api/v1/progress/learner-001", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["progress"] == nil {
		t.Fatal("expected progress field")
	}
}

// TestKnowledgeGraphEndpoint 测试知识图谱
func TestKnowledgeGraphEndpoint(t *testing.T) {
	r, userStore := newTestRouter()
	handler := r.Setup()

	hash, _ := auth.HashPassword("pass123")
	user, _ := userStore.CreateUser("kg@test.com", hash, auth.RoleStudent, "default")
	token, _ := auth.CreateAccessToken(r.jwtSecret, user.ID, user.Email, string(user.Role), user.TenantID, user.LearnerID)

	req := httptest.NewRequest("GET", "/api/v1/knowledge-graph", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp["nodes"] == nil {
		t.Fatal("expected nodes field")
	}
	if resp["order"] == nil {
		t.Fatal("expected order field")
	}
}

// TestUnauthorizedAccess 测试未认证访问
func TestUnauthorizedAccess(t *testing.T) {
	r, _ := newTestRouter()
	handler := r.Setup()

	// 访问需要认证的端点
	req := httptest.NewRequest("GET", "/api/v1/notifications", nil)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", w.Code)
	}
}

// TestForbiddenAccess 测试权限不足
func TestForbiddenAccess(t *testing.T) {
	r, userStore := newTestRouter()
	handler := r.Setup()

	// 创建 student 用户
	hash, _ := auth.HashPassword("pass123")
	student, _ := userStore.CreateUser("student@test.com", hash, auth.RoleStudent, "default")
	studentToken, _ := auth.CreateAccessToken(r.jwtSecret, student.ID, student.Email, string(student.Role), student.TenantID, student.LearnerID)

	// 访问 admin 端点
	req := httptest.NewRequest("GET", "/api/v1/tenants", nil)
	req.Header.Set("Authorization", "Bearer "+studentToken)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if w.Code != http.StatusForbidden {
		t.Fatalf("expected 403, got %d", w.Code)
	}
}
