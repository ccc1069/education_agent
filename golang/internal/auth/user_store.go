package auth

import (
	"fmt"
	"sync"
	"time"
)

// User 用户实体
type User struct {
	ID           string    `json:"id"`
	Email        string    `json:"email"`
	PasswordHash string    `json:"-"`
	Role         Role      `json:"role"`
	TenantID     string    `json:"tenant_id"`
	LearnerID    string    `json:"learner_id"`
	CreatedAt    time.Time `json:"created_at"`
}

// UserStore 内存用户存储（可选 SQLite 回写）。
//
// 面试要点:
// - 默认内存,重启丢失;接 persist 后 Create 会落盘
// - 使用 sync.RWMutex 支持并发
// - 支持 email 唯一性检查
type UserStore struct {
	mu          sync.RWMutex
	users       map[string]*User
	byEmail     map[string]string // email -> userID
	persistHook func(*User) error
}

// NewUserStore 创建用户存储
func NewUserStore() *UserStore {
	return &UserStore{
		users:   make(map[string]*User),
		byEmail: make(map[string]string),
	}
}

// SetPersistHook 注册创建用户后的持久化回调。
func (s *UserStore) SetPersistHook(hook func(*User) error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.persistHook = hook
}

// ImportUser 从持久化层导入（不触发 hook）。
func (s *UserStore) ImportUser(u *User) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, exists := s.byEmail[u.Email]; exists {
		return fmt.Errorf("email already registered: %s", u.Email)
	}
	cp := *u
	s.users[u.ID] = &cp
	s.byEmail[u.Email] = u.ID
	return nil
}

// CreateUser 创建用户
func (s *UserStore) CreateUser(email, passwordHash string, role Role, tenantID string) (*User, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	// 检查 email 唯一性
	if _, exists := s.byEmail[email]; exists {
		return nil, fmt.Errorf("email already registered: %s", email)
	}

	user := &User{
		ID:           generateUserID(),
		Email:        email,
		PasswordHash: passwordHash,
		Role:         role,
		TenantID:     tenantID,
		LearnerID:    generateUserID(), // 默认 learnerID
		CreatedAt:    time.Now(),
	}

	s.users[user.ID] = user
	s.byEmail[email] = user.ID

	if s.persistHook != nil {
		if err := s.persistHook(user); err != nil {
			delete(s.users, user.ID)
			delete(s.byEmail, email)
			return nil, err
		}
	}

	return user, nil
}

// Authenticate 验证用户凭据
func (s *UserStore) Authenticate(email, password string) (*User, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	userID, ok := s.byEmail[email]
	if !ok {
		return nil, false
	}

	user := s.users[userID]
	if !VerifyPassword(user.PasswordHash, password) {
		return nil, false
	}

	return user, true
}

// GetUser 获取用户
func (s *UserStore) GetUser(id string) (*User, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	user, ok := s.users[id]
	return user, ok
}

// GetUserByEmail 通过 email 查找用户
func (s *UserStore) GetUserByEmail(email string) (*User, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	userID, ok := s.byEmail[email]
	if !ok {
		return nil, false
	}
	return s.users[userID], true
}

// DeleteUser 删除用户
func (s *UserStore) DeleteUser(id string) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if user, ok := s.users[id]; ok {
		delete(s.byEmail, user.Email)
		delete(s.users, id)
	}
}

// Count 获取用户总数
func (s *UserStore) Count() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return len(s.users)
}

// generateUserID 生成用户 ID
func generateUserID() string {
	return "user-" + generateID()
}
