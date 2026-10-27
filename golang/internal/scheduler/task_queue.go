package scheduler

import (
	"context"
	"sync"
	"time"
)

// TaskHandler 任务处理函数
type TaskHandler func(task Task) error

// Task 异步任务
type Task struct {
	ID          string                 `json:"id"`
	Name        string                 `json:"name"`
	Payload     map[string]interface{} `json:"payload"`
	Attempt     int                    `json:"attempt"`
	MaxAttempts int                    `json:"max_attempts"`
	Backoff     time.Duration          `json:"backoff"`
	CreatedAt   time.Time              `json:"created_at"`
}

// TaskExecution 任务执行记录
type TaskExecution struct {
	TaskID    string    `json:"task_id"`
	Name      string    `json:"name"`
	Status    string    `json:"status"` // success / failed
	Error     string    `json:"error,omitempty"`
	Duration  int64     `json:"duration_ms"`
	Timestamp time.Time `json:"timestamp"`
}

// QueueStats 队列统计
type QueueStats struct {
	QueueLen    int `json:"queue_len"`
	QueueCap    int `json:"queue_cap"`
	Workers     int `json:"workers"`
	DeadLetters int `json:"dead_letters"`
}

// TaskQueue 异步任务队列
//
// 面试要点:
// - Channel-based worker pool
// - 支持重试 + 指数退避
// - 死信队列 (超过最大重试次数)
type TaskQueue struct {
	mu          sync.Mutex
	tasks       chan Task
	handlers    map[string]TaskHandler
	workers     int
	deadLetters []Task
	history     []TaskExecution
	done        chan struct{}
	wg          sync.WaitGroup
}

// NewTaskQueue 创建任务队列
func NewTaskQueue(workers, bufferSize int) *TaskQueue {
	if workers <= 0 {
		workers = 4
	}
	if bufferSize <= 0 {
		bufferSize = 100
	}
	return &TaskQueue{
		tasks:       make(chan Task, bufferSize),
		handlers:    make(map[string]TaskHandler),
		workers:     workers,
		deadLetters: make([]Task, 0),
		history:     make([]TaskExecution, 0),
		done:        make(chan struct{}),
	}
}

// RegisterHandler 注册任务处理器
func (q *TaskQueue) RegisterHandler(name string, handler TaskHandler) {
	q.mu.Lock()
	defer q.mu.Unlock()
	q.handlers[name] = handler
}

// Enqueue 入队任务 (非阻塞)
func (q *TaskQueue) Enqueue(task Task) error {
	if task.MaxAttempts <= 0 {
		task.MaxAttempts = 3
	}
	if task.Backoff <= 0 {
		task.Backoff = time.Second
	}
	if task.CreatedAt.IsZero() {
		task.CreatedAt = time.Now()
	}

	select {
	case q.tasks <- task:
		return nil
	case <-q.done:
		return ErrQueueStopped
	default:
		return ErrQueueFull
	}
}

// EnqueueBlocking 入队任务 (阻塞等待)
func (q *TaskQueue) EnqueueBlocking(task Task) error {
	if task.MaxAttempts <= 0 {
		task.MaxAttempts = 3
	}
	if task.Backoff <= 0 {
		task.Backoff = time.Second
	}
	if task.CreatedAt.IsZero() {
		task.CreatedAt = time.Now()
	}

	select {
	case q.tasks <- task:
		return nil
	case <-q.done:
		return ErrQueueStopped
	}
}

// Start 启动 worker pool
func (q *TaskQueue) Start(ctx context.Context) {
	for i := 0; i < q.workers; i++ {
		q.wg.Add(1)
		go q.worker(ctx, i)
	}
}

// Stop 停止 worker pool
func (q *TaskQueue) Stop() {
	close(q.done)
	q.wg.Wait()
}

// worker 工作 goroutine
func (q *TaskQueue) worker(ctx context.Context, id int) {
	defer q.wg.Done()

	for {
		select {
		case <-ctx.Done():
			return
		case <-q.done:
			// 处理完剩余任务
			for {
				select {
				case task, ok := <-q.tasks:
					if !ok {
						return
					}
					q.processTask(task)
				default:
					return
				}
			}
		case task, ok := <-q.tasks:
			if !ok {
				return
			}
			q.processTask(task)
		}
	}
}

// processTask 处理单个任务
func (q *TaskQueue) processTask(task Task) {
	q.mu.Lock()
	handler, ok := q.handlers[task.Name]
	q.mu.Unlock()

	if !ok {
		return
	}

	start := time.Now()
	err := handler(task)
	duration := time.Since(start).Milliseconds()

	exec := TaskExecution{
		TaskID:    task.ID,
		Name:      task.Name,
		Duration:  duration,
		Timestamp: time.Now(),
	}
	if err != nil {
		exec.Status = "failed"
		exec.Error = err.Error()
	} else {
		exec.Status = "success"
	}
	q.mu.Lock()
	q.history = append(q.history, exec)
	q.mu.Unlock()

	if err != nil && task.Attempt < task.MaxAttempts {
		// 重试
		task.Attempt++
		time.Sleep(task.Backoff * time.Duration(1<<uint(task.Attempt-1)))
		// 使用阻塞入队,但检查 done
		q.EnqueueBlocking(task)
	} else if err != nil {
		// 超过最大重试,加入死信队列
		q.mu.Lock()
		q.deadLetters = append(q.deadLetters, task)
		q.mu.Unlock()
	}
}

// Stats 获取队列统计
func (q *TaskQueue) Stats() QueueStats {
	q.mu.Lock()
	defer q.mu.Unlock()
	return QueueStats{
		QueueLen:    len(q.tasks),
		QueueCap:    cap(q.tasks),
		Workers:     q.workers,
		DeadLetters: len(q.deadLetters),
	}
}

// GetHistory 获取执行历史
func (q *TaskQueue) GetHistory() []TaskExecution {
	q.mu.Lock()
	defer q.mu.Unlock()
	result := make([]TaskExecution, len(q.history))
	copy(result, q.history)
	return result
}

// ListRegisteredTasks 列出已注册的任务名
func (q *TaskQueue) ListRegisteredTasks() []string {
	q.mu.Lock()
	defer q.mu.Unlock()
	names := make([]string, 0, len(q.handlers))
	for name := range q.handlers {
		names = append(names, name)
	}
	return names
}

// GetDeadLetters 获取死信队列
func (q *TaskQueue) GetDeadLetters() []Task {
	q.mu.Lock()
	defer q.mu.Unlock()

	result := make([]Task, len(q.deadLetters))
	copy(result, q.deadLetters)
	return result
}

// ErrQueueFull 队列已满错误
var ErrQueueFull = &queueFullError{}

type queueFullError struct{}

func (e *queueFullError) Error() string {
	return "task queue is full"
}

// ErrQueueStopped 队列已停止错误
var ErrQueueStopped = &queueStoppedError{}

type queueStoppedError struct{}

func (e *queueStoppedError) Error() string {
	return "task queue is stopped"
}
