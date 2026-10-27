package scheduler

import (
	"context"
	"sync/atomic"
	"testing"
	"time"
)

func TestTaskQueue_EnqueueAndProcess(t *testing.T) {
	queue := NewTaskQueue(2, 10)

	var processed int32
	queue.RegisterHandler("test", func(task Task) error {
		atomic.AddInt32(&processed, 1)
		return nil
	})

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	queue.Start(ctx)

	// 入队 5 个任务
	for i := 0; i < 5; i++ {
		err := queue.Enqueue(Task{ID: "t1", Name: "test"})
		if err != nil {
			t.Fatalf("Enqueue failed: %v", err)
		}
	}

	// 等待处理
	time.Sleep(500 * time.Millisecond)
	cancel()
	queue.Stop()

	if atomic.LoadInt32(&processed) != 5 {
		t.Errorf("processed: got %d, want 5", processed)
	}
}

func TestTaskQueue_Retry(t *testing.T) {
	queue := NewTaskQueue(1, 10)

	var attempts int32
	queue.RegisterHandler("flaky", func(task Task) error {
		atomic.AddInt32(&attempts, 1)
		if atomic.LoadInt32(&attempts) < 3 {
			return ErrQueueFull // 模拟失败
		}
		return nil
	})

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	queue.Start(ctx)

	// 使用小退避,确保 3 次重试能在时间内完成
	queue.Enqueue(Task{ID: "t1", Name: "flaky", MaxAttempts: 3, Backoff: 100 * time.Millisecond})

	time.Sleep(2 * time.Second)
	cancel()
	queue.Stop()

	if atomic.LoadInt32(&attempts) != 3 {
		t.Errorf("attempts: got %d, want 3", attempts)
	}
}

func TestTaskQueue_DeadLetter(t *testing.T) {
	queue := NewTaskQueue(1, 10)

	queue.RegisterHandler("always-fail", func(task Task) error {
		return ErrQueueFull
	})

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	queue.Start(ctx)

	// 使用小退避,确保重试能在时间内完成
	// MaxAttempts=2: 初始 + 1 次重试,退避 100ms
	queue.Enqueue(Task{ID: "t1", Name: "always-fail", MaxAttempts: 2, Backoff: 100 * time.Millisecond})

	time.Sleep(1 * time.Second)
	cancel()
	queue.Stop()

	dead := queue.GetDeadLetters()
	if len(dead) != 1 {
		t.Errorf("dead letters: got %d, want 1", len(dead))
	}
}

func TestScheduler_RegisterAndRun(t *testing.T) {
	s := NewScheduler()

	var count int32
	s.RegisterInterval("tick", 50*time.Millisecond, func() {
		atomic.AddInt32(&count, 1)
	})

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go s.Start(ctx)

	time.Sleep(250 * time.Millisecond)
	s.Stop()

	// 250ms / 50ms = 5 次,但停止可能延迟,至少应执行 2 次
	if atomic.LoadInt32(&count) < 2 {
		t.Errorf("count: got %d, want >= 2", count)
	}
}

func TestScheduler_Unregister(t *testing.T) {
	s := NewScheduler()

	s.RegisterInterval("task1", time.Minute, func() {})
	s.RegisterInterval("task2", time.Minute, func() {})

	if len(s.ListTasks()) != 2 {
		t.Errorf("tasks: got %d, want 2", len(s.ListTasks()))
	}

	s.Unregister("task1")
	if len(s.ListTasks()) != 1 {
		t.Errorf("after unregister: got %d, want 1", len(s.ListTasks()))
	}
}
