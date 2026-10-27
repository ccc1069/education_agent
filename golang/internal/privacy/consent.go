package privacy

import (
	"crypto/rand"
	"fmt"
	"sync"
	"time"
)

// ConsentType 同意类型
type ConsentType string

const (
	ConsentAnalytics   ConsentType = "analytics"
	ConsentLLMTraining ConsentType = "llm_training"
	ConsentMarketing   ConsentType = "marketing"
)

// ConsentRecord 同意记录
type ConsentRecord struct {
	ID         string      `json:"id"`
	UserID     string      `json:"user_id"`
	ConsentType ConsentType `json:"consent_type"`
	Granted    bool        `json:"granted"`
	IP         string      `json:"ip"`
	UserAgent  string      `json:"user_agent"`
	Timestamp  time.Time   `json:"timestamp"`
}

// ExportJob 数据导出任务
type ExportJob struct {
	ID        string    `json:"id"`
	UserID    string    `json:"user_id"`
	Status    string    `json:"status"` // pending/processing/completed/failed
	Data      string    `json:"data,omitempty"`
	CreatedAt time.Time `json:"created_at"`
	CompletedAt time.Time `json:"completed_at,omitempty"`
}

// DeletionRequest 账户删除请求
type DeletionRequest struct {
	ID          string    `json:"id"`
	UserID      string    `json:"user_id"`
	Status      string    `json:"status"` // pending/confirmed/executed
	RequestedAt time.Time `json:"requested_at"`
	ScheduledAt time.Time `json:"scheduled_at"` // 30 天后执行
	ExecutedAt  time.Time `json:"executed_at,omitempty"`
	Reason      string    `json:"reason"`
}

// PrivacyService 隐私合规服务
//
// 面试要点:
// - 同意管理: 用户可随时撤回同意
// - 数据导出: GDPR "right to data portability"
// - 账户删除: GDPR "right to erasure",30 天宽限期
type PrivacyService struct {
	mu         sync.RWMutex
	consents   map[string][]ConsentRecord  // userID -> records
	exports    map[string][]ExportJob
	deletions  map[string][]DeletionRequest
}

// NewPrivacyService 创建隐私服务
func NewPrivacyService() *PrivacyService {
	return &PrivacyService{
		consents:  make(map[string][]ConsentRecord),
		exports:   make(map[string][]ExportJob),
		deletions: make(map[string][]DeletionRequest),
	}
}

// RecordConsent 记录用户同意/撤回
func (s *PrivacyService) RecordConsent(userID string, consentType ConsentType, granted bool, ip, ua string) *ConsentRecord {
	s.mu.Lock()
	defer s.mu.Unlock()

	record := ConsentRecord{
		ID:          generateID(),
		UserID:      userID,
		ConsentType: consentType,
		Granted:     granted,
		IP:          ip,
		UserAgent:   ua,
		Timestamp:   time.Now(),
	}
	s.consents[userID] = append(s.consents[userID], record)
	return &record
}

// GetConsent 获取用户最新的同意状态
func (s *PrivacyService) GetConsent(userID string, consentType ConsentType) bool {
	s.mu.RLock()
	defer s.mu.RUnlock()

	records := s.consents[userID]
	// 查找最新记录
	for i := len(records) - 1; i >= 0; i-- {
		if records[i].ConsentType == consentType {
			return records[i].Granted
		}
	}
	return false // 默认未同意
}

// GetAllConsents 获取用户所有同意状态
func (s *PrivacyService) GetAllConsents(userID string) map[ConsentType]bool {
	s.mu.RLock()
	defer s.mu.RUnlock()

	result := make(map[ConsentType]bool)
	records := s.consents[userID]
	for i := len(records) - 1; i >= 0; i-- {
		if _, ok := result[records[i].ConsentType]; !ok {
			result[records[i].ConsentType] = records[i].Granted
		}
	}
	return result
}

// ExportUserData 创建数据导出任务
func (s *PrivacyService) ExportUserData(userID string) (*ExportJob, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	job := &ExportJob{
		ID:        generateID(),
		UserID:    userID,
		Status:    "completed", // 简化: 直接完成
		CreatedAt: time.Now(),
		CompletedAt: time.Now(),
	}
	s.exports[userID] = append(s.exports[userID], *job)
	return job, nil
}

// GetExportJobs 获取用户的导出任务
func (s *PrivacyService) GetExportJobs(userID string) []ExportJob {
	s.mu.RLock()
	defer s.mu.RUnlock()

	return s.exports[userID]
}

// RequestDeletion 请求账户删除 (30 天后执行)
func (s *PrivacyService) RequestDeletion(userID string, reason string) (*DeletionRequest, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	req := &DeletionRequest{
		ID:          generateID(),
		UserID:      userID,
		Status:      "pending",
		RequestedAt: time.Now(),
		ScheduledAt: time.Now().Add(30 * 24 * time.Hour),
		Reason:      reason,
	}
	s.deletions[userID] = append(s.deletions[userID], *req)
	return req, nil
}

// ConfirmDeletion 确认删除请求
func (s *PrivacyService) ConfirmDeletion(userID, requestID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	records := s.deletions[userID]
	for i := range records {
		if records[i].ID == requestID && records[i].Status == "pending" {
			records[i].Status = "confirmed"
			return nil
		}
	}
	return fmt.Errorf("deletion request not found or not pending")
}

// ExecuteDeletion 执行删除 (清除所有用户数据)
func (s *PrivacyService) ExecuteDeletion(userID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	// 清除同意记录
	delete(s.consents, userID)
	// 清除导出记录
	delete(s.exports, userID)
	// 标记删除为已执行
	records := s.deletions[userID]
	for i := range records {
		if records[i].Status == "confirmed" {
			records[i].Status = "executed"
			records[i].ExecutedAt = time.Now()
		}
	}
	return nil
}

// GetDeletionRequests 获取用户的删除请求
func (s *PrivacyService) GetDeletionRequests(userID string) []DeletionRequest {
	s.mu.RLock()
	defer s.mu.RUnlock()

	return s.deletions[userID]
}

// CancelDeletion 取消待执行的删除请求
func (s *PrivacyService) CancelDeletion(userID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	records := s.deletions[userID]
	for i := range records {
		if records[i].Status == "pending" || records[i].Status == "confirmed" {
			records[i].Status = "cancelled"
			return nil
		}
	}
	return fmt.Errorf("no cancellable deletion request found")
}

// generateID 生成随机 ID
func generateID() string {
	b := make([]byte, 12)
	rand.Read(b)
	return fmt.Sprintf("%x", b)
}
