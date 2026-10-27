package auth

import (
	"testing"
)

func TestUserStore_CreateUser(t *testing.T) {
	store := NewUserStore()

	hash, _ := HashPassword("password123")
	user, err := store.CreateUser("alice@example.com", hash, RoleStudent, "tenant-001")
	if err != nil {
		t.Fatalf("CreateUser failed: %v", err)
	}
	if user.Email != "alice@example.com" {
		t.Errorf("email: got %s, want alice@example.com", user.Email)
	}
	if user.Role != RoleStudent {
		t.Errorf("role: got %s, want student", user.Role)
	}
	if user.ID == "" {
		t.Error("user ID should not be empty")
	}
}

func TestUserStore_DuplicateEmail(t *testing.T) {
	store := NewUserStore()

	hash, _ := HashPassword("password123")
	store.CreateUser("alice@example.com", hash, RoleStudent, "tenant-001")

	_, err := store.CreateUser("alice@example.com", hash, RoleStudent, "tenant-001")
	if err == nil {
		t.Error("should fail with duplicate email")
	}
}

func TestUserStore_Authenticate(t *testing.T) {
	store := NewUserStore()

	hash, _ := HashPassword("password123")
	store.CreateUser("alice@example.com", hash, RoleStudent, "tenant-001")

	// 正确凭据
	user, ok := store.Authenticate("alice@example.com", "password123")
	if !ok {
		t.Error("should authenticate with correct credentials")
	}
	if user.Email != "alice@example.com" {
		t.Errorf("email: got %s, want alice@example.com", user.Email)
	}

	// 错误密码
	_, ok = store.Authenticate("alice@example.com", "wrongpassword")
	if ok {
		t.Error("should not authenticate with wrong password")
	}

	// 不存在的用户
	_, ok = store.Authenticate("nobody@example.com", "password123")
	if ok {
		t.Error("should not authenticate nonexistent user")
	}
}

func TestUserStore_GetUser(t *testing.T) {
	store := NewUserStore()

	hash, _ := HashPassword("password123")
	user, _ := store.CreateUser("alice@example.com", hash, RoleStudent, "tenant-001")

	got, ok := store.GetUser(user.ID)
	if !ok {
		t.Error("should get user by ID")
	}
	if got.Email != "alice@example.com" {
		t.Errorf("email: got %s", got.Email)
	}

	// 不存在
	_, ok = store.GetUser("nonexistent")
	if ok {
		t.Error("should not get nonexistent user")
	}
}

func TestUserStore_DeleteUser(t *testing.T) {
	store := NewUserStore()

	hash, _ := HashPassword("password123")
	user, _ := store.CreateUser("alice@example.com", hash, RoleStudent, "tenant-001")

	store.DeleteUser(user.ID)

	if store.Count() != 0 {
		t.Errorf("count: got %d, want 0", store.Count())
	}

	// 删除后可以重新注册
	store.CreateUser("alice@example.com", hash, RoleStudent, "tenant-001")
	if store.Count() != 1 {
		t.Errorf("count: got %d, want 1", store.Count())
	}
}
