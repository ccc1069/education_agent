package notification

import (
	"crypto/rand"
	"fmt"
	"sync"
	"time"

	"multi-agent-education/golang/internal/ratelimit"
)

// NotificationChannel 通知渠道
type NotificationChannel string

const (
	ChannelWS     NotificationChannel = "ws"
	ChannelEmail  NotificationChannel = "email"
	ChannelPush   NotificationChannel = "push"
)

// NotificationStatus 通知状态
type NotificationStatus string

const (
	StatusUnread NotificationStatus = "unread"
	StatusRead   NotificationStatus = "read"
	StatusSent   NotificationStatus = "sent"
)

// Notification 通知
type Notification struct {
	ID        string                 `json:"id"`
	UserID    string                 `json:"user_id"`
	Type      string                 `json:"type"`
	Title     string                 `json:"title"`
	Content   string                 `json:"content"`
	Priority  int                    `json:"priority"` // 1-5
	Channel   NotificationChannel    `json:"channel"`
	Status    NotificationStatus     `json:"status"`
	Metadata  map[string]interface{} `json:"metadata"`
	CreatedAt time.Time              `json:"created_at"`
}

// NotificationPreference 通知偏好
type NotificationPreference struct {
	UserID          string                     `json:"user_id"`
	QuietHoursStart int                        `json:"quiet_hours_start"` // 0-23, -1 表示关闭
	QuietHoursEnd   int                        `json:"quiet_hours_end"`   // 0-23
	ChannelPrefs    map[NotificationChannel]bool `json:"channel_prefs"`
}

// NotificationService 通知服务
//
// 面试要点:
// - 多渠道通知 (ws/email/push)
// - 勿扰时段 (quiet hours)
// - 频率限制 (per-user)
type NotificationService struct {
	mu          sync.RWMutex
	notifications map[string][]Notification
	preferences   map[string]NotificationPreference
	rateLimiter   *ratelimit.SlidingWindowLimiter
}

// NewNotificationService 创建通知服务
func NewNotificationService() *NotificationService {
	return &NotificationService{
		notifications: make(map[string][]Notification),
		preferences:   make(map[string]NotificationPreference),
		rateLimiter:   ratelimit.NewSlidingWindowLimiter(10, time.Minute), // 10/min per user
	}
}

// Send 发送通知
func (s *NotificationService) Send(userID, nType, title, content string, priority int, channel NotificationChannel) error {
	// 频率限制
	if allowed, _, _ := s.rateLimiter.Allow(userID); !allowed {
		return fmt.Errorf("rate limit exceeded for user %s", userID)
	}

	// 检查勿扰时段
	if s.inQuietHours(userID) && priority < 4 {
		// 低优先级通知在勿扰时段静默丢弃
		return nil
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	notification := Notification{
		ID:        generateID(),
		UserID:    userID,
		Type:      nType,
		Title:     title,
		Content:   content,
		Priority:  priority,
		Channel:   channel,
		Status:    StatusUnread,
		CreatedAt: time.Now(),
	}

	s.notifications[userID] = append(s.notifications[userID], notification)
	return nil
}

// GetUnread 获取未读通知
func (s *NotificationService) GetUnread(userID string) []Notification {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var result []Notification
	for _, n := range s.notifications[userID] {
		if n.Status == StatusUnread {
			result = append(result, n)
		}
	}
	return result
}

// GetAll 获取用户所有通知
func (s *NotificationService) GetAll(userID string) []Notification {
	s.mu.RLock()
	defer s.mu.RUnlock()

	result := make([]Notification, len(s.notifications[userID]))
	copy(result, s.notifications[userID])
	return result
}

// MarkRead 标记已读
func (s *NotificationService) MarkRead(notificationID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	for userID, notifications := range s.notifications {
		for i, n := range notifications {
			if n.ID == notificationID {
				s.notifications[userID][i].Status = StatusRead
				return nil
			}
		}
	}
	return fmt.Errorf("notification not found: %s", notificationID)
}

// MarkAllRead 标记用户所有通知已读
func (s *NotificationService) MarkAllRead(userID string) {
	s.mu.Lock()
	defer s.mu.Unlock()

	for i := range s.notifications[userID] {
		s.notifications[userID][i].Status = StatusRead
	}
}

// SetPreference 设置通知偏好
func (s *NotificationService) SetPreference(pref NotificationPreference) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.preferences[pref.UserID] = pref
}

// GetPreference 获取通知偏好
func (s *NotificationService) GetPreference(userID string) NotificationPreference {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.preferences[userID]
}

// inQuietHours 检查是否在勿扰时段
func (s *NotificationService) inQuietHours(userID string) bool {
	pref, ok := s.preferences[userID]
	if !ok {
		return false
	}
	if pref.QuietHoursStart < 0 || pref.QuietHoursEnd < 0 {
		return false
	}

	now := time.Now().Hour()
	if pref.QuietHoursStart <= pref.QuietHoursEnd {
		return now >= pref.QuietHoursStart && now < pref.QuietHoursEnd
	}
	// 跨午夜: 22:00 - 06:00
	return now >= pref.QuietHoursStart || now < pref.QuietHoursEnd
}

// generateID 生成随机 ID
func generateID() string {
	b := make([]byte, 12)
	rand.Read(b)
	return fmt.Sprintf("notif-%x", b)
}
