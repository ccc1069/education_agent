package scheduler

import (
	"context"
	"sync"
	"time"
)

// ScheduledTask 定时任务
type ScheduledTask struct {
	Name     string
	Interval time.Duration
	Fn       func()
	NextRun  time.Time
}

// Scheduler 定时任务调度器
//
// 面试要点:
// - 基于 time.Ticker 的周期调度
// - 支持动态注册/注销
// - 优雅关闭
type Scheduler struct {
	mu    sync.Mutex
	tasks map[string]*ScheduledTask
	done  chan struct{}
}

// NewScheduler 创建调度器
func NewScheduler() *Scheduler {
	return &Scheduler{
		tasks: make(map[string]*ScheduledTask),
		done:  make(chan struct{}),
	}
}

// RegisterInterval 注册间隔任务
func (s *Scheduler) RegisterInterval(name string, interval time.Duration, fn func()) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.tasks[name] = &ScheduledTask{
		Name:     name,
		Interval: interval,
		Fn:       fn,
		NextRun:  time.Now().Add(interval),
	}
}

// Unregister 注销任务
func (s *Scheduler) Unregister(name string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.tasks, name)
}

// Start 启动调度器
func (s *Scheduler) Start(ctx context.Context) {
	ticker := time.NewTicker(10 * time.Millisecond) // 10ms 精度
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-s.done:
			return
		case now := <-ticker.C:
			s.runDueTasks(now)
		}
	}
}

// runDueTasks 执行到期任务
func (s *Scheduler) runDueTasks(now time.Time) {
	s.mu.Lock()
	defer s.mu.Unlock()

	for _, task := range s.tasks {
		if now.After(task.NextRun) || now.Equal(task.NextRun) {
			task.NextRun = now.Add(task.Interval)
			// 异步执行,避免阻塞调度
			go task.Fn()
		}
	}
}

// Stop 停止调度器
func (s *Scheduler) Stop() {
	close(s.done)
}

// ListTasks 列出所有定时任务
func (s *Scheduler) ListTasks() []ScheduledTask {
	s.mu.Lock()
	defer s.mu.Unlock()

	result := make([]ScheduledTask, 0, len(s.tasks))
	for _, task := range s.tasks {
		result = append(result, *task)
	}
	return result
}
