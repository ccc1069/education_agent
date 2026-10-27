package audit

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"sync"
	"time"
)

// AuditLog 审计日志条目
//
// 面试要点:
// - HMAC-SHA256 链式哈希,确保不可篡改
// - curr_hash = HMAC(secret, prev_hash || id || actor || action || target || timestamp)
// - VerifyChain() 可检测任何历史记录篡改
type AuditLog struct {
	ID        string                 `json:"id"`
	TenantID  string                 `json:"tenant_id"`
	Actor     string                 `json:"actor"`
	Action    string                 `json:"action"`
	Target    string                 `json:"target"`
	IP        string                 `json:"ip"`
	UserAgent string                 `json:"user_agent"`
	Metadata  map[string]interface{} `json:"metadata"`
	Timestamp time.Time              `json:"timestamp"`
	PrevHash  string                 `json:"prev_hash"`
	CurrHash  string                 `json:"curr_hash"`
}

// AuditService 审计日志服务
type AuditService struct {
	mu          sync.RWMutex
	logs        []AuditLog
	secret      []byte
	lastHash    string
	persistHook func(*AuditLog) error
}

// NewAuditService 创建审计服务
func NewAuditService(secret []byte) *AuditService {
	if len(secret) == 0 {
		secret = []byte("default-audit-secret-change-in-production")
	}
	return &AuditService{
		logs:     make([]AuditLog, 0),
		secret:   secret,
		lastHash: "",
	}
}

// SetPersistHook 注册落盘回调。
func (s *AuditService) SetPersistHook(hook func(*AuditLog) error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.persistHook = hook
}

// SetLastHash 从 DB 恢复链尾。
func (s *AuditService) SetLastHash(hash string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.lastHash = hash
}

// LogAction 记录审计日志
func (s *AuditService) LogAction(tenantID, actor, action, target, ip, ua string, metadata map[string]interface{}) *AuditLog {
	s.mu.Lock()

	log := AuditLog{
		ID:        generateID(),
		TenantID:  tenantID,
		Actor:     actor,
		Action:    action,
		Target:    target,
		IP:        ip,
		UserAgent: ua,
		Metadata:  metadata,
		Timestamp: time.Now(),
		PrevHash:  s.lastHash,
	}

	log.CurrHash = s.computeHash(log)
	s.lastHash = log.CurrHash
	s.logs = append(s.logs, log)
	hook := s.persistHook
	s.mu.Unlock()

	if hook != nil {
		cp := log
		_ = hook(&cp)
	}
	out := log
	return &out
}

// VerifyChain 验证审计链完整性
//
// 返回 (valid, brokenAt)
// - valid=true: 链完整
// - valid=false: brokenAt 为第一个被破坏的日志 ID
func (s *AuditService) VerifyChain() (valid bool, brokenAt string) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var prevHash string
	for _, log := range s.logs {
		if log.PrevHash != prevHash {
			return false, log.ID
		}
		expectedHash := s.computeHash(log)
		if log.CurrHash != expectedHash {
			return false, log.ID
		}
		prevHash = log.CurrHash
	}
	return true, ""
}

// GetLogs 获取租户的审计日志
func (s *AuditService) GetLogs(tenantID string, limit int) []AuditLog {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var filtered []AuditLog
	for i := len(s.logs) - 1; i >= 0; i-- {
		if s.logs[i].TenantID == tenantID {
			filtered = append(filtered, s.logs[i])
			if limit > 0 && len(filtered) >= limit {
				break
			}
		}
	}
	// 反转,按时间正序
	for i, j := 0, len(filtered)-1; i < j; i, j = i+1, j-1 {
		filtered[i], filtered[j] = filtered[j], filtered[i]
	}
	return filtered
}

// GetAllLogs 获取所有日志 (admin only)
func (s *AuditService) GetAllLogs(limit int) []AuditLog {
	s.mu.RLock()
	defer s.mu.RUnlock()

	if limit <= 0 || limit > len(s.logs) {
		limit = len(s.logs)
	}
	result := make([]AuditLog, limit)
	copy(result, s.logs[len(s.logs)-limit:])
	return result
}

// computeHash 计算日志的 HMAC-SHA256 哈希
func (s *AuditService) computeHash(log AuditLog) string {
	// 构造输入: prev_hash || id || actor || action || target || timestamp
	input := fmt.Sprintf("%s|%s|%s|%s|%s|%d",
		log.PrevHash, log.ID, log.Actor, log.Action, log.Target,
		log.Timestamp.UnixNano())

	// 包含 metadata (如果有)
	if log.Metadata != nil {
		metaJSON, _ := json.Marshal(log.Metadata)
		input += "|" + string(metaJSON)
	}

	h := hmac.New(sha256.New, s.secret)
	h.Write([]byte(input))
	return base64.RawURLEncoding.EncodeToString(h.Sum(nil))
}

// generateID 生成随机 ID
func generateID() string {
	b := make([]byte, 12)
	rand.Read(b)
	return fmt.Sprintf("%x", b)
}
