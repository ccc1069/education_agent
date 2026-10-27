package auth

import (
	"crypto/rand"
	"crypto/sha256"
	"fmt"
	"sync"
	"time"
)

// RefreshToken 刷新令牌 (存储哈希,不存明文)
//
// 面试要点:
// - 存储 SHA-256 哈希而非明文 token
// - 轮换时旧 token 立即撤销,签发新 token
// - 支持按用户撤销全部 token (密码修改/账号锁定)
type RefreshToken struct {
	TokenHash string    `json:"token_hash"`
	UserID    string    `json:"user_id"`
	ExpiresAt time.Time `json:"expires_at"`
	CreatedAt time.Time `json:"created_at"`
	Revoked   bool      `json:"revoked"`
}

// RefreshTokenStore 刷新令牌存储
type RefreshTokenStore struct {
	mu          sync.RWMutex
	tokens      map[string]*RefreshToken // tokenHash -> token
	byUser      map[string][]string      // userID -> []tokenHash
	persistHook func(*RefreshToken) error
}

// NewRefreshTokenStore 创建刷新令牌存储
func NewRefreshTokenStore() *RefreshTokenStore {
	return &RefreshTokenStore{
		tokens: make(map[string]*RefreshToken),
		byUser: make(map[string][]string),
	}
}

// SetPersistHook 注册落盘回调。
func (s *RefreshTokenStore) SetPersistHook(hook func(*RefreshToken) error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.persistHook = hook
}

// ImportToken 从 DB 导入（不触发 hook）。
func (s *RefreshTokenStore) ImportToken(rt *RefreshToken) {
	s.mu.Lock()
	defer s.mu.Unlock()
	cp := *rt
	s.tokens[rt.TokenHash] = &cp
	s.byUser[rt.UserID] = append(s.byUser[rt.UserID], rt.TokenHash)
}

func (s *RefreshTokenStore) persist(rt *RefreshToken) {
	s.mu.RLock()
	hook := s.persistHook
	s.mu.RUnlock()
	if hook != nil && rt != nil {
		_ = hook(rt)
	}
}

// Create 创建刷新令牌
// 返回明文 token (仅此时可获取),内部存储 SHA-256 哈希
func (s *RefreshTokenStore) Create(userID string, ttl time.Duration) (string, error) {
	// 生成 32 字节随机 token
	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		return "", fmt.Errorf("generate random: %w", err)
	}
	token := fmt.Sprintf("rt-%x", raw)

	// 存储哈希
	hash := sha256Hex(token)

	s.mu.Lock()
	s.tokens[hash] = &RefreshToken{
		TokenHash: hash,
		UserID:    userID,
		ExpiresAt: time.Now().Add(ttl),
		CreatedAt: time.Now(),
		Revoked:   false,
	}
	s.byUser[userID] = append(s.byUser[userID], hash)
	rt := s.tokens[hash]
	s.mu.Unlock()
	s.persist(rt)
	return token, nil
}

// Rotate 轮换刷新令牌
// 验证旧 token → 撤销 → 签发新 token
// 返回 (newToken, userID, error)
func (s *RefreshTokenStore) Rotate(oldToken string) (string, string, error) {
	hash := sha256Hex(oldToken)

	s.mu.Lock()

	rt, ok := s.tokens[hash]
	if !ok {
		s.mu.Unlock()
		return "", "", ErrInvalidToken
	}
	if rt.Revoked {
		s.revokeAllLocked(rt.UserID)
		s.mu.Unlock()
		return "", "", fmt.Errorf("token reused: possible theft")
	}
	if time.Now().After(rt.ExpiresAt) {
		s.mu.Unlock()
		return "", "", ErrTokenExpired
	}

	rt.Revoked = true
	oldCopy := *rt

	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		s.mu.Unlock()
		return "", "", fmt.Errorf("generate random: %w", err)
	}
	newToken := fmt.Sprintf("rt-%x", raw)
	newHash := sha256Hex(newToken)

	s.tokens[newHash] = &RefreshToken{
		TokenHash: newHash,
		UserID:    rt.UserID,
		ExpiresAt: time.Now().Add(DefaultRefreshDuration),
		CreatedAt: time.Now(),
		Revoked:   false,
	}
	s.byUser[rt.UserID] = append(s.byUser[rt.UserID], newHash)
	newCopy := *s.tokens[newHash]
	userID := rt.UserID
	s.mu.Unlock()

	s.persist(&oldCopy)
	s.persist(&newCopy)
	return newToken, userID, nil
}

// Revoke 撤销指定 token
func (s *RefreshTokenStore) Revoke(token string) {
	hash := sha256Hex(token)

	s.mu.Lock()
	if rt, ok := s.tokens[hash]; ok {
		rt.Revoked = true
		cp := *rt
		s.mu.Unlock()
		s.persist(&cp)
		return
	}
	s.mu.Unlock()
}

// RevokeAll 撤销用户全部 token
func (s *RefreshTokenStore) RevokeAll(userID string) {
	s.mu.Lock()
	var copies []*RefreshToken
	for _, hash := range s.byUser[userID] {
		if rt, ok := s.tokens[hash]; ok {
			rt.Revoked = true
			cp := *rt
			copies = append(copies, &cp)
		}
	}
	s.mu.Unlock()
	for _, cp := range copies {
		s.persist(cp)
	}
}

// revokeAllLocked 内部方法 (需持有写锁)
func (s *RefreshTokenStore) revokeAllLocked(userID string) {
	for _, hash := range s.byUser[userID] {
		if rt, ok := s.tokens[hash]; ok {
			rt.Revoked = true
		}
	}
}

// Cleanup 清理过期的 token
func (s *RefreshTokenStore) Cleanup() {
	s.mu.Lock()
	defer s.mu.Unlock()

	now := time.Now()
	for hash, rt := range s.tokens {
		if now.After(rt.ExpiresAt) || rt.Revoked {
			delete(s.tokens, hash)
		}
	}
}

// sha256Hex 计算 SHA-256 哈希的 hex 表示
func sha256Hex(input string) string {
	h := sha256.Sum256([]byte(input))
	return fmt.Sprintf("%x", h)
}
