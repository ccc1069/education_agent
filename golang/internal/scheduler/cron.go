package scheduler

import (
	"fmt"
	"strconv"
	"strings"
	"time"
)

// CronSchedule 5 字段 cron 表达式
//
// 格式: "分 时 日 月 周"
// 分: 0-59, 时: 0-23, 日: 1-31, 月: 1-12, 周: 0-6 (0=周日)
//
// 支持:
// - * 通配
// - , 列表 (e.g. "1,3,5")
// - - 范围 (e.g. "1-5")
// - / 步长 (e.g. "*/15" 表示每 15 分钟)
type CronSchedule struct {
	Expression string
	Minutes    map[int]bool
	Hours      map[int]bool
	Days       map[int]bool
	Months     map[int]bool
	Weekdays   map[int]bool
}

// ParseCron 解析 5 字段 cron 表达式
func ParseCron(expr string) (*CronSchedule, error) {
	fields := strings.Fields(expr)
	if len(fields) != 5 {
		return nil, fmt.Errorf("cron expression must have 5 fields, got %d: %q", len(fields), expr)
	}

	minutes, err := parseField(fields[0], 0, 59)
	if err != nil {
		return nil, fmt.Errorf("invalid minutes field: %w", err)
	}
	hours, err := parseField(fields[1], 0, 23)
	if err != nil {
		return nil, fmt.Errorf("invalid hours field: %w", err)
	}
	days, err := parseField(fields[2], 1, 31)
	if err != nil {
		return nil, fmt.Errorf("invalid days field: %w", err)
	}
	months, err := parseField(fields[3], 1, 12)
	if err != nil {
		return nil, fmt.Errorf("invalid months field: %w", err)
	}
	weekdays, err := parseField(fields[4], 0, 6)
	if err != nil {
		return nil, fmt.Errorf("invalid weekdays field: %w", err)
	}

	return &CronSchedule{
		Expression: expr,
		Minutes:    minutes,
		Hours:      hours,
		Days:       days,
		Months:     months,
		Weekdays:   weekdays,
	}, nil
}

// parseField 解析单个 cron 字段
func parseField(field string, min, max int) (map[int]bool, error) {
	result := make(map[int]bool)

	// 处理列表 (,)
	parts := strings.Split(field, ",")
	for _, part := range parts {
		if err := parsePart(part, min, max, result); err != nil {
			return nil, err
		}
	}

	return result, nil
}

// parsePart 解析单个字段的部分 (可能包含 - 和 /)
func parsePart(part string, min, max int, result map[int]bool) error {
	// 处理步长 (/)
	step := 1
	if idx := strings.Index(part, "/"); idx != nilInt() {
		stepStr := part[idx+1:]
		var err error
		step, err = strconv.Atoi(stepStr)
		if err != nil || step <= 0 {
			return fmt.Errorf("invalid step: %s", stepStr)
		}
		part = part[:idx]
	}

	// 处理范围 (-)
	if part == "*" {
		// 通配
		for i := min; i <= max; i += step {
			result[i] = true
		}
		return nil
	}

	if idx := strings.Index(part, "-"); idx >= 0 {
		// 范围
		start, err := strconv.Atoi(part[:idx])
		if err != nil {
			return fmt.Errorf("invalid range start: %s", part[:idx])
		}
		end, err := strconv.Atoi(part[idx+1:])
		if err != nil {
			return fmt.Errorf("invalid range end: %s", part[idx+1:])
		}
		if start < min || end > max || start > end {
			return fmt.Errorf("range out of bounds: %d-%d (valid: %d-%d)", start, end, min, max)
		}
		for i := start; i <= end; i += step {
			result[i] = true
		}
		return nil
	}

	// 单个值
	val, err := strconv.Atoi(part)
	if err != nil {
		return fmt.Errorf("invalid value: %s", part)
	}
	if val < min || val > max {
		return fmt.Errorf("value out of bounds: %d (valid: %d-%d)", val, min, max)
	}
	result[val] = true
	return nil
}

// nilInt 返回 -1 作为 strings.Index 未找到的标记
func nilInt() int {
	return -1
}

// Matches 检查给定时间是否匹配 cron 表达式
func (c *CronSchedule) Matches(t time.Time) bool {
	if !c.Minutes[t.Minute()] {
		return false
	}
	if !c.Hours[t.Hour()] {
		return false
	}
	if !c.Days[t.Day()] {
		return false
	}
	if !c.Months[int(t.Month())] {
		return false
	}
	if !c.Weekdays[int(t.Weekday())] {
		return false
	}
	return true
}

// NextRun 返回给定时间之后的下一次运行时间
func (c *CronSchedule) NextRun(after time.Time) time.Time {
	t := after.Add(1 * time.Minute)
	t = time.Date(t.Year(), t.Month(), t.Day(), t.Hour(), t.Minute(), 0, 0, t.Location())

	// 最多搜索 4 年 (考虑闰年)
	maxSearch := after.AddDate(4, 0, 0)
	for t.Before(maxSearch) {
		if c.Matches(t) {
			return t
		}
		t = t.Add(1 * time.Minute)
	}
	return after // 未找到
}

// RegisterCron 注册 cron 任务到调度器
func (s *Scheduler) RegisterCron(name, cronExpr string, fn func()) error {
	schedule, err := ParseCron(cronExpr)
	if err != nil {
		return err
	}

	// 计算首次运行时间
	nextRun := schedule.NextRun(time.Now())

	// 包装函数: 执行后重新计算下次运行时间
	wrappedFn := func() {
		fn()
		// 更新下次运行时间
		s.mu.Lock()
		if task, ok := s.tasks[name]; ok {
			task.NextRun = schedule.NextRun(time.Now())
		}
		s.mu.Unlock()
	}

	s.mu.Lock()
	s.tasks[name] = &ScheduledTask{
		Name:     name,
		Interval: 0, // cron 任务不使用固定间隔
		Fn:       wrappedFn,
		NextRun:  nextRun,
	}
	s.mu.Unlock()

	return nil
}
