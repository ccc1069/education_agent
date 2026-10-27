package notification

import (
	"testing"
	"time"
)

func TestNotificationService_Send(t *testing.T) {
	service := NewNotificationService()

	err := service.Send("user-001", "reminder", "学习提醒", "该复习了", 3, ChannelWS)
	if err != nil {
		t.Fatalf("Send failed: %v", err)
	}

	// 验证未读
	unread := service.GetUnread("user-001")
	if len(unread) != 1 {
		t.Errorf("unread: got %d, want 1", len(unread))
	}
	if unread[0].Title != "学习提醒" {
		t.Errorf("title: got %s, want 学习提醒", unread[0].Title)
	}
}

func TestNotificationService_MarkRead(t *testing.T) {
	service := NewNotificationService()

	service.Send("user-001", "test", "标题", "内容", 3, ChannelWS)

	unread := service.GetUnread("user-001")
	if len(unread) != 1 {
		t.Fatalf("expected 1 unread, got %d", len(unread))
	}

	// 标记已读
	err := service.MarkRead(unread[0].ID)
	if err != nil {
		t.Fatalf("MarkRead failed: %v", err)
	}

	unread = service.GetUnread("user-001")
	if len(unread) != 0 {
		t.Errorf("after mark read: got %d, want 0", len(unread))
	}
}

func TestNotificationService_MarkAllRead(t *testing.T) {
	service := NewNotificationService()

	service.Send("user-001", "test", "标题1", "内容1", 3, ChannelWS)
	service.Send("user-001", "test", "标题2", "内容2", 3, ChannelWS)

	service.MarkAllRead("user-001")

	unread := service.GetUnread("user-001")
	if len(unread) != 0 {
		t.Errorf("after mark all read: got %d, want 0", len(unread))
	}
}

func TestNotificationService_RateLimit(t *testing.T) {
	service := NewNotificationService()

	// 发送 10 个 (达到限制)
	for i := 0; i < 10; i++ {
		service.Send("user-001", "test", "标题", "内容", 3, ChannelWS)
	}

	// 第 11 个应被限流
	err := service.Send("user-001", "test", "标题", "内容", 3, ChannelWS)
	if err == nil {
		t.Error("should be rate limited after 10 notifications")
	}
}

func TestNotificationService_QuietHours(t *testing.T) {
	service := NewNotificationService()

	// 设置勿扰时段: 当前时间前后 1 小时
	now := time.Now().Hour()
	start := (now - 1 + 24) % 24
	end := (now + 1) % 24

	service.SetPreference(NotificationPreference{
		UserID:          "user-001",
		QuietHoursStart: start,
		QuietHoursEnd:   end,
	})

	// 低优先级通知在勿扰时段应被静默丢弃
	err := service.Send("user-001", "test", "标题", "内容", 2, ChannelWS)
	if err != nil {
		t.Errorf("low priority in quiet hours should not error: %v", err)
	}

	// 验证没有通知被创建
	all := service.GetAll("user-001")
	if len(all) != 0 {
		t.Errorf("low priority in quiet hours should be dropped, got %d", len(all))
	}

	// 高优先级 (priority >= 4) 应正常发送
	service.Send("user-001", "urgent", "紧急", "内容", 5, ChannelWS)
	all = service.GetAll("user-001")
	if len(all) != 1 {
		t.Errorf("high priority should be sent, got %d", len(all))
	}
}

func TestNotificationService_GetAll(t *testing.T) {
	service := NewNotificationService()

	service.Send("user-001", "test", "标题1", "内容1", 3, ChannelWS)
	service.Send("user-001", "test", "标题2", "内容2", 3, ChannelWS)
	service.Send("user-002", "test", "标题3", "内容3", 3, ChannelWS)

	all := service.GetAll("user-001")
	if len(all) != 2 {
		t.Errorf("user-001 notifications: got %d, want 2", len(all))
	}

	all = service.GetAll("user-002")
	if len(all) != 1 {
		t.Errorf("user-002 notifications: got %d, want 1", len(all))
	}
}

func TestNotificationService_SetPreference(t *testing.T) {
	service := NewNotificationService()

	pref := NotificationPreference{
		UserID:          "user-001",
		QuietHoursStart: 22,
		QuietHoursEnd:   6,
		ChannelPrefs: map[NotificationChannel]bool{
			ChannelWS:    true,
			ChannelEmail: false,
		},
	}
	service.SetPreference(pref)

	got := service.GetPreference("user-001")
	if got.QuietHoursStart != 22 || got.QuietHoursEnd != 6 {
		t.Errorf("quiet hours: got %d-%d, want 22-6", got.QuietHoursStart, got.QuietHoursEnd)
	}
	if !got.ChannelPrefs[ChannelWS] {
		t.Error("ws channel should be enabled")
	}
}
