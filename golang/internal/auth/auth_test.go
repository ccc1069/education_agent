package auth

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

var testSecret Key = []byte("test-secret-key-for-unit-tests-32bytes!")

func TestCreateAndParseToken(t *testing.T) {
	claims := Claims{
		UserID:    "user-001",
		Email:     "test@example.com",
		Role:      "student",
		TenantID:  "tenant-001",
		TokenType: "access",
		ExpiresAt: time.Now().Add(time.Hour),
	}

	token, err := CreateToken(testSecret, claims)
	if err != nil {
		t.Fatalf("CreateToken failed: %v", err)
	}

	// 验证格式: header.payload.signature
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		t.Fatalf("expected 3 parts, got %d", len(parts))
	}

	parsed, err := ParseToken(testSecret, token)
	if err != nil {
		t.Fatalf("ParseToken failed: %v", err)
	}

	if parsed.UserID != claims.UserID {
		t.Errorf("UserID: got %s, want %s", parsed.UserID, claims.UserID)
	}
	if parsed.Email != claims.Email {
		t.Errorf("Email: got %s, want %s", parsed.Email, claims.Email)
	}
	if parsed.Role != claims.Role {
		t.Errorf("Role: got %s, want %s", parsed.Role, claims.Role)
	}
	if parsed.TenantID != claims.TenantID {
		t.Errorf("TenantID: got %s, want %s", parsed.TenantID, claims.TenantID)
	}
}

func TestParseToken_InvalidSignature(t *testing.T) {
	claims := Claims{
		UserID:    "user-001",
		ExpiresAt: time.Now().Add(time.Hour),
	}
	token, _ := CreateToken(testSecret, claims)

	wrongSecret := Key([]byte("wrong-secret-key-for-unit-tests-32bytes"))
	_, err := ParseToken(wrongSecret, token)
	if err != ErrInvalidSign {
		t.Errorf("expected ErrInvalidSign, got %v", err)
	}
}

func TestParseToken_Expired(t *testing.T) {
	claims := Claims{
		UserID:    "user-001",
		ExpiresAt: time.Now().Add(-time.Hour), // 已过期
	}
	token, _ := CreateToken(testSecret, claims)

	_, err := ParseToken(testSecret, token)
	if err != ErrTokenExpired {
		t.Errorf("expected ErrTokenExpired, got %v", err)
	}
}

func TestParseToken_InvalidFormat(t *testing.T) {
	_, err := ParseToken(testSecret, "invalid.token")
	if err != ErrInvalidFormat {
		t.Errorf("expected ErrInvalidFormat, got %v", err)
	}
}

func TestCreateAccessToken(t *testing.T) {
	token, err := CreateAccessToken(testSecret, "user-001", "test@example.com", "student", "tenant-001", "user-001")
	if err != nil {
		t.Fatalf("CreateAccessToken failed: %v", err)
	}

	parsed, err := ParseToken(testSecret, token)
	if err != nil {
		t.Fatalf("ParseToken failed: %v", err)
	}

	if parsed.TokenType != "access" {
		t.Errorf("TokenType: got %s, want access", parsed.TokenType)
	}
	if time.Until(parsed.ExpiresAt) > 31*time.Minute {
		t.Errorf("ExpiresAt too far in future: %v", parsed.ExpiresAt)
	}
}

func TestCreateRefreshToken(t *testing.T) {
	token, err := CreateRefreshToken(testSecret, "user-001", "tenant-001")
	if err != nil {
		t.Fatalf("CreateRefreshToken failed: %v", err)
	}

	parsed, err := ParseToken(testSecret, token)
	if err != nil {
		t.Fatalf("ParseToken failed: %v", err)
	}

	if parsed.TokenType != "refresh" {
		t.Errorf("TokenType: got %s, want refresh", parsed.TokenType)
	}
	if time.Until(parsed.ExpiresAt) < 6*24*time.Hour {
		t.Errorf("ExpiresAt too soon: %v", parsed.ExpiresAt)
	}
}

func TestHashPassword(t *testing.T) {
	password := "securePassword123"
	hash, err := HashPassword(password)
	if err != nil {
		t.Fatalf("HashPassword failed: %v", err)
	}

	// 哈希不应等于原密码
	if hash == password {
		t.Error("hash should not equal password")
	}

	// 验证正确密码
	if !VerifyPassword(hash, password) {
		t.Error("VerifyPassword should return true for correct password")
	}

	// 验证错误密码
	if VerifyPassword(hash, "wrongPassword") {
		t.Error("VerifyPassword should return false for wrong password")
	}
}

func TestVerifyPassword_DifferentHashes(t *testing.T) {
	password := "test123"
	hash1, _ := HashPassword(password)
	hash2, _ := HashPassword(password)

	// bcrypt 每次加盐不同,哈希应不同
	if hash1 == hash2 {
		t.Error("bcrypt should generate different hashes for same password")
	}

	// 但都应验证通过
	if !VerifyPassword(hash1, password) || !VerifyPassword(hash2, password) {
		t.Error("both hashes should verify correctly")
	}
}

func TestRBAC_HasRole(t *testing.T) {
	user := &CurrentUser{ID: "u1", Role: RoleStudent}

	if !HasRole(user, RoleStudent) {
		t.Error("should have student role")
	}
	if HasRole(user, RoleAdmin) {
		t.Error("should not have admin role")
	}
	if !HasRole(user, RoleStudent, RoleAdmin) {
		t.Error("should match one of multiple roles")
	}
	if HasRole(nil, RoleStudent) {
		t.Error("nil user should have no roles")
	}
}

func TestRBAC_HasMinRole(t *testing.T) {
	teacher := &CurrentUser{ID: "u1", Role: RoleTeacher}
	student := &CurrentUser{ID: "u2", Role: RoleStudent}
	admin := &CurrentUser{ID: "u3", Role: RoleAdmin}

	// teacher >= teacher
	if !HasMinRole(teacher, RoleTeacher) {
		t.Error("teacher should meet teacher minimum")
	}
	// student < teacher
	if HasMinRole(student, RoleTeacher) {
		t.Error("student should not meet teacher minimum")
	}
	// admin >= teacher
	if !HasMinRole(admin, RoleTeacher) {
		t.Error("admin should meet teacher minimum")
	}
	// admin >= admin
	if !HasMinRole(admin, RoleAdmin) {
		t.Error("admin should meet admin minimum")
	}
}

func TestRBAC_IsAdmin(t *testing.T) {
	if IsAdmin(&CurrentUser{Role: RoleStudent}) {
		t.Error("student is not admin")
	}
	if !IsAdmin(&CurrentUser{Role: RoleAdmin}) {
		t.Error("admin is admin")
	}
}

func TestAuthMiddleware(t *testing.T) {
	// 创建受保护的处理程序
	handler := AuthMiddleware(testSecret)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		user := GetUserFromContext(r.Context())
		if user == nil {
			http.Error(w, "no user", http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(user.ID))
	}))

	// 测试 1: 无 token
	req := httptest.NewRequest("GET", "/protected", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusUnauthorized {
		t.Errorf("no token: got %d, want 401", rr.Code)
	}

	// 测试 2: 有效 token
	token, _ := CreateAccessToken(testSecret, "user-001", "test@example.com", "student", "tenant-001", "user-001")
	req = httptest.NewRequest("GET", "/protected", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rr = httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Errorf("valid token: got %d, want 200: %s", rr.Code, rr.Body.String())
	}
	if rr.Body.String() != "user-001" {
		t.Errorf("body: got %s, want user-001", rr.Body.String())
	}

	// 测试 3: 无效 token
	req = httptest.NewRequest("GET", "/protected", nil)
	req.Header.Set("Authorization", "Bearer invalid.token.here")
	rr = httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusUnauthorized {
		t.Errorf("invalid token: got %d, want 401", rr.Code)
	}
}

func TestRequireRole(t *testing.T) {
	handler := AuthMiddleware(testSecret)(
		RequireRole(RoleAdmin)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
		})),
	)

	// student 访问 admin 路由
	token, _ := CreateAccessToken(testSecret, "user-001", "test@example.com", "student", "tenant-001", "user-001")
	req := httptest.NewRequest("GET", "/admin", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusForbidden {
		t.Errorf("student->admin: got %d, want 403", rr.Code)
	}

	// admin 访问 admin 路由
	token, _ = CreateAccessToken(testSecret, "admin-001", "admin@example.com", "admin", "tenant-001", "admin-001")
	req = httptest.NewRequest("GET", "/admin", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rr = httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Errorf("admin->admin: got %d, want 200", rr.Code)
	}
}

func TestExtractBearerToken(t *testing.T) {
	tests := []struct {
		name   string
		header string
		want   string
	}{
		{"valid", "Bearer abc123", "abc123"},
		{"empty", "", ""},
		{"no bearer", "Basic abc", ""},
		{"lowercase", "bearer abc123", "abc123"},
		{"with spaces", "Bearer  abc123  ", "abc123"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			r := httptest.NewRequest("GET", "/", nil)
			r.Header.Set("Authorization", tt.header)
			got := extractBearerToken(r)
			if got != tt.want {
				t.Errorf("got %q, want %q", got, tt.want)
			}
		})
	}
}
