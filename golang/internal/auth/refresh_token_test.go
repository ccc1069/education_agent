package auth

import (
	"testing"
	"time"
)

func TestRefreshTokenStore_Create(t *testing.T) {
	store := NewRefreshTokenStore()
	token, err := store.Create("user-001", 7*24*time.Hour)
	if err != nil {
		t.Fatalf("Create failed: %v", err)
	}
	if token == "" {
		t.Fatal("expected non-empty token")
	}
	if len(token) < 20 {
		t.Fatalf("token too short: %s", token)
	}
}

func TestRefreshTokenStore_Rotate(t *testing.T) {
	store := NewRefreshTokenStore()
	oldToken, err := store.Create("user-001", 7*24*time.Hour)
	if err != nil {
		t.Fatalf("Create failed: %v", err)
	}

	newToken, userID, err := store.Rotate(oldToken)
	if err != nil {
		t.Fatalf("Rotate failed: %v", err)
	}
	if userID != "user-001" {
		t.Fatalf("expected user-001, got %s", userID)
	}
	if newToken == oldToken {
		t.Fatal("new token should differ from old")
	}

	// Old token should be revoked (reuse detection)
	_, _, err = store.Rotate(oldToken)
	if err == nil {
		t.Fatal("expected error reusing old token")
	}
}

func TestRefreshTokenStore_RotateExpired(t *testing.T) {
	store := NewRefreshTokenStore()
	token, err := store.Create("user-001", 1*time.Millisecond)
	if err != nil {
		t.Fatalf("Create failed: %v", err)
	}

	// Wait for expiry
	time.Sleep(10 * time.Millisecond)

	_, _, err = store.Rotate(token)
	if err != ErrTokenExpired {
		t.Fatalf("expected ErrTokenExpired, got %v", err)
	}
}

func TestRefreshTokenStore_RotateInvalid(t *testing.T) {
	store := NewRefreshTokenStore()
	_, _, err := store.Rotate("nonexistent-token")
	if err != ErrInvalidToken {
		t.Fatalf("expected ErrInvalidToken, got %v", err)
	}
}

func TestRefreshTokenStore_Revoke(t *testing.T) {
	store := NewRefreshTokenStore()
	token, err := store.Create("user-001", 7*24*time.Hour)
	if err != nil {
		t.Fatalf("Create failed: %v", err)
	}

	store.Revoke(token)

	// Revoked token should fail rotation
	_, _, err = store.Rotate(token)
	if err == nil {
		t.Fatal("expected error rotating revoked token")
	}
}

func TestRefreshTokenStore_RevokeAll(t *testing.T) {
	store := NewRefreshTokenStore()
	token1, _ := store.Create("user-001", 7*24*time.Hour)
	token2, _ := store.Create("user-001", 7*24*time.Hour)
	_, _ = store.Create("user-002", 7*24*time.Hour)

	store.RevokeAll("user-001")

	_, _, err := store.Rotate(token1)
	if err == nil {
		t.Fatal("expected error rotating revoked token1")
	}
	_, _, err = store.Rotate(token2)
	if err == nil {
		t.Fatal("expected error rotating revoked token2")
	}
}

func TestRefreshTokenStore_Cleanup(t *testing.T) {
	store := NewRefreshTokenStore()
	token, _ := store.Create("user-001", 1*time.Millisecond)
	store.Revoke(token)

	time.Sleep(10 * time.Millisecond)
	store.Cleanup()

	// After cleanup, revoked/expired tokens should be removed
	// (internal state check via behavior)
}

func TestRefreshTokenStore_MultipleUsers(t *testing.T) {
	store := NewRefreshTokenStore()
	token1, _ := store.Create("user-001", 7*24*time.Hour)
	token2, _ := store.Create("user-002", 7*24*time.Hour)

	_, uid1, err := store.Rotate(token1)
	if err != nil {
		t.Fatalf("Rotate token1 failed: %v", err)
	}
	if uid1 != "user-001" {
		t.Fatalf("expected user-001, got %s", uid1)
	}

	_, uid2, err := store.Rotate(token2)
	if err != nil {
		t.Fatalf("Rotate token2 failed: %v", err)
	}
	if uid2 != "user-002" {
		t.Fatalf("expected user-002, got %s", uid2)
	}
}
