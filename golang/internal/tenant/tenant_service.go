package tenant

import (
	"crypto/rand"
	"fmt"
	"sync"
	"time"
)

// Tenant 租户
type Tenant struct {
	ID        string    `json:"id"`
	Name      string    `json:"name"`
	Slug      string    `json:"slug"`
	Plan      string    `json:"plan"` // free/pro/enterprise
	IsActive  bool      `json:"is_active"`
	CreatedAt time.Time `json:"created_at"`
}

// TenantQuota 租户配额
type TenantQuota struct {
	TenantID       string `json:"tenant_id"`
	MaxUsers       int    `json:"max_users"`
	MaxLLMTokens   int    `json:"max_llm_tokens_per_month"`
	CurrentTokens  int    `json:"current_llm_tokens"`
}

// TenantService 租户管理服务
//
// 面试要点:
// - 多租户隔离 (共享数据库,行级隔离)
// - 配额管理 (LLM token 月度限额)
// - 软删除 (标记 is_active=false)
type TenantService struct {
	mu      sync.RWMutex
	tenants map[string]*Tenant
	quotas  map[string]*TenantQuota
	bySlug  map[string]string // slug -> tenantID
}

// NewTenantService 创建租户服务
func NewTenantService() *TenantService {
	return &TenantService{
		tenants: make(map[string]*Tenant),
		quotas:  make(map[string]*TenantQuota),
		bySlug:  make(map[string]string),
	}
}

// CreateTenant 创建租户
func (s *TenantService) CreateTenant(name, slug, plan string) (*Tenant, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if _, ok := s.bySlug[slug]; ok {
		return nil, fmt.Errorf("tenant slug already exists: %s", slug)
	}
	if plan == "" {
		plan = "free"
	}

	tenant := &Tenant{
		ID:        generateID(),
		Name:      name,
		Slug:      slug,
		Plan:      plan,
		IsActive:  true,
		CreatedAt: time.Now(),
	}
	s.tenants[tenant.ID] = tenant
	s.bySlug[slug] = tenant.ID
	s.quotas[tenant.ID] = &TenantQuota{
		TenantID:     tenant.ID,
		MaxUsers:     10,
		MaxLLMTokens: 100000,
	}
	return tenant, nil
}

// GetTenant 获取租户
func (s *TenantService) GetTenant(id string) (*Tenant, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	t, ok := s.tenants[id]
	if !ok {
		return nil, fmt.Errorf("tenant not found: %s", id)
	}
	return t, nil
}

// UpdateTenant 更新租户
func (s *TenantService) UpdateTenant(id, name, plan string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	t, ok := s.tenants[id]
	if !ok {
		return fmt.Errorf("tenant not found: %s", id)
	}
	if name != "" {
		t.Name = name
	}
	if plan != "" {
		t.Plan = plan
	}
	return nil
}

// DeleteTenant 软删除租户
func (s *TenantService) DeleteTenant(id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	t, ok := s.tenants[id]
	if !ok {
		return fmt.Errorf("tenant not found: %s", id)
	}
	t.IsActive = false
	return nil
}

// ListTenants 列出所有活跃租户
func (s *TenantService) ListTenants() []*Tenant {
	s.mu.RLock()
	defer s.mu.RUnlock()

	result := make([]*Tenant, 0)
	for _, t := range s.tenants {
		if t.IsActive {
			result = append(result, t)
		}
	}
	return result
}

// GetQuota 获取租户配额
func (s *TenantService) GetQuota(tenantID string) (*TenantQuota, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	q, ok := s.quotas[tenantID]
	if !ok {
		return nil, fmt.Errorf("quota not found for tenant: %s", tenantID)
	}
	return q, nil
}

// UpdateQuota 更新配额
func (s *TenantService) UpdateQuota(tenantID string, maxUsers, maxTokens int) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	q, ok := s.quotas[tenantID]
	if !ok {
		return fmt.Errorf("quota not found for tenant: %s", tenantID)
	}
	if maxUsers > 0 {
		q.MaxUsers = maxUsers
	}
	if maxTokens > 0 {
		q.MaxLLMTokens = maxTokens
	}
	return nil
}

// ResetQuota 重置月度用量
func (s *TenantService) ResetQuota(tenantID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	q, ok := s.quotas[tenantID]
	if !ok {
		return fmt.Errorf("quota not found for tenant: %s", tenantID)
	}
	q.CurrentTokens = 0
	return nil
}

// generateID 生成随机 ID
func generateID() string {
	b := make([]byte, 12)
	rand.Read(b)
	return fmt.Sprintf("tnt-%x", b)
}
