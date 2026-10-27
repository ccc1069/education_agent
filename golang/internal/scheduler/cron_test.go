package scheduler

import (
	"testing"
	"time"
)

func TestParseCron_Valid(t *testing.T) {
	tests := []struct {
		expr     string
		wantErr  bool
	}{
		{"*/15 * * * *", false},    // 每 15 分钟
		{"0 0 * * *", false},       // 每天 0:00
		{"30 8 * * 1-5", false},    // 工作日 8:30
		{"0 0 1 * *", false},       // 每月 1 号 0:00
		{"0 0 1 1 *", false},       // 每年 1 月 1 号
		{"0,15,30,45 * * * *", false}, // 每 15 分钟 (列表)
		{"* * * * *", false},       // 每分钟
		{"5 0 * * *", false},       // 每天 0:05
		{"17 6 * * *", false},      // 每天 6:17
		{"0 12 * * 0", false},      // 每周日 12:00
		{"0 0 * * 1,3,5", false},   // 周一三五 0:00
		{"0", true},                // 字段不足
		{"* * * * * *", true},      // 字段过多
		{"abc * * * *", true},      // 无效值
		{"60 * * * *", true},       // 分钟越界
		{"* 24 * * *", true},       // 小时越界
		{"* * 0 * *", true},        // 日期越界 (0)
		{"* * 32 * *", true},       // 日期越界 (32)
		{"* * * 0 *", true},        // 月份越界 (0)
		{"* * * 13 *", true},       // 月份越界 (13)
		{"* * * * 7", true},        // 星期越界 (7)
	}

	for _, tt := range tests {
		t.Run(tt.expr, func(t *testing.T) {
			_, err := ParseCron(tt.expr)
			if (err != nil) != tt.wantErr {
				t.Errorf("ParseCron(%q) error = %v, wantErr %v", tt.expr, err, tt.wantErr)
			}
		})
	}
}

func TestCronSchedule_Matches(t *testing.T) {
	// 每天 8:30
	schedule, err := ParseCron("30 8 * * *")
	if err != nil {
		t.Fatalf("ParseCron failed: %v", err)
	}

	// 2026-07-30 08:30:00 周四
	matchTime := time.Date(2026, 7, 30, 8, 30, 0, 0, time.UTC)
	if !schedule.Matches(matchTime) {
		t.Error("expected match at 8:30")
	}

	// 2026-07-30 08:31:00 不应匹配
	noMatchTime := time.Date(2026, 7, 30, 8, 31, 0, 0, time.UTC)
	if schedule.Matches(noMatchTime) {
		t.Error("expected no match at 8:31")
	}
}

func TestCronSchedule_MatchesWeekday(t *testing.T) {
	// 工作日 9:00
	schedule, err := ParseCron("0 9 * * 1-5")
	if err != nil {
		t.Fatalf("ParseCron failed: %v", err)
	}

	// 2026-07-30 周四 9:00 应匹配
	thursday := time.Date(2026, 7, 30, 9, 0, 0, 0, time.UTC)
	if !schedule.Matches(thursday) {
		t.Error("expected match on Thursday 9:00")
	}

	// 2026-07-25 周六 9:00 不应匹配
	saturday := time.Date(2026, 7, 25, 9, 0, 0, 0, time.UTC)
	if schedule.Matches(saturday) {
		t.Error("expected no match on Saturday 9:00")
	}

	// 2026-07-26 周日 9:00 不应匹配
	sunday := time.Date(2026, 7, 26, 9, 0, 0, 0, time.UTC)
	if schedule.Matches(sunday) {
		t.Error("expected no match on Sunday 9:00")
	}
}

func TestCronSchedule_MatchesStep(t *testing.T) {
	// 每 15 分钟
	schedule, err := ParseCron("*/15 * * * *")
	if err != nil {
		t.Fatalf("ParseCron failed: %v", err)
	}

	// 0, 15, 30, 45 分应匹配
	for _, min := range []int{0, 15, 30, 45} {
		tm := time.Date(2026, 7, 30, 10, min, 0, 0, time.UTC)
		if !schedule.Matches(tm) {
			t.Errorf("expected match at :%02d", min)
		}
	}

	// 其他分钟不应匹配
	for _, min := range []int{1, 5, 10, 14, 16, 29, 31, 44, 46, 59} {
		tm := time.Date(2026, 7, 30, 10, min, 0, 0, time.UTC)
		if schedule.Matches(tm) {
			t.Errorf("expected no match at :%02d", min)
		}
	}
}

func TestCronSchedule_MatchesList(t *testing.T) {
	// 第 0, 15, 30, 45 分钟
	schedule, err := ParseCron("0,15,30,45 * * * *")
	if err != nil {
		t.Fatalf("ParseCron failed: %v", err)
	}

	for _, min := range []int{0, 15, 30, 45} {
		tm := time.Date(2026, 7, 30, 10, min, 0, 0, time.UTC)
		if !schedule.Matches(tm) {
			t.Errorf("expected match at :%02d", min)
		}
	}

	tm := time.Date(2026, 7, 30, 10, 5, 0, 0, time.UTC)
	if schedule.Matches(tm) {
		t.Error("expected no match at :05")
	}
}

func TestCronSchedule_NextRun(t *testing.T) {
	// 每小时第 30 分钟
	schedule, err := ParseCron("30 * * * *")
	if err != nil {
		t.Fatalf("ParseCron failed: %v", err)
	}

	// 从 8:00 开始,下次运行应为 8:30
	now := time.Date(2026, 7, 30, 8, 0, 0, 0, time.UTC)
	next := schedule.NextRun(now)
	expected := time.Date(2026, 7, 30, 8, 30, 0, 0, time.UTC)
	if !next.Equal(expected) {
		t.Errorf("expected next run at %v, got %v", expected, next)
	}

	// 从 8:30 开始,下次运行应为 9:30
	now = time.Date(2026, 7, 30, 8, 30, 0, 0, time.UTC)
	next = schedule.NextRun(now)
	expected = time.Date(2026, 7, 30, 9, 30, 0, 0, time.UTC)
	if !next.Equal(expected) {
		t.Errorf("expected next run at %v, got %v", expected, next)
	}
}

func TestScheduler_RegisterCron(t *testing.T) {
	s := NewScheduler()

	err := s.RegisterCron("test-cron", "*/5 * * * *", func() {})
	if err != nil {
		t.Fatalf("RegisterCron failed: %v", err)
	}

	tasks := s.ListTasks()
	if len(tasks) != 1 {
		t.Fatalf("expected 1 task, got %d", len(tasks))
	}
	if tasks[0].Name != "test-cron" {
		t.Errorf("expected task name 'test-cron', got %s", tasks[0].Name)
	}
}

func TestScheduler_RegisterCronInvalid(t *testing.T) {
	s := NewScheduler()
	err := s.RegisterCron("bad", "invalid cron expr", func() {})
	if err == nil {
		t.Fatal("expected error for invalid cron expression")
	}
}

func TestCronSchedule_MatchesMonth(t *testing.T) {
	// 每月 1 号 0:00
	schedule, err := ParseCron("0 0 1 * *")
	if err != nil {
		t.Fatalf("ParseCron failed: %v", err)
	}

	// 1 号应匹配
	first := time.Date(2026, 7, 1, 0, 0, 0, 0, time.UTC)
	if !schedule.Matches(first) {
		t.Error("expected match on 1st")
	}

	// 2 号不应匹配
	second := time.Date(2026, 7, 2, 0, 0, 0, 0, time.UTC)
	if schedule.Matches(second) {
		t.Error("expected no match on 2nd")
	}
}
