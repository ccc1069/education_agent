package api

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"multi-agent-education/golang/internal/eventbus"
)

// EnhancedSSEManager 增强型 SSE 管理器 -- 对齐 Java WebSocket 重连能力
//
// 核心功能:
// - 全局单调序号: 每个出站事件附加 seq (globalSequence.Add(1))
// - 重连回放: 客户端传 Last-Event-ID: N → 从 retainedEvents 中找 seq > N 的事件重放
// - 事件缓存: 每学习者保留最近 100 条事件(环形缓冲)
// - 心跳: 每 30s 发送 :heartbeat\n\n 注释
// - 历史: 新连接发送最近 10 条 + 后续实时
//
// SSE 格式:
// seq: 42
// event: tutor.teaching_response
// data: {"seq":42,"id":"...","type":"tutor.teaching_response",...}
type EnhancedSSEManager struct {
	mu                sync.RWMutex
	clients           map[string][]*sseClient
	globalSequence    atomic.Int64
	retainedEvents    map[string]*ringBuffer // 每学习者事件缓存
	heartbeatInterval time.Duration
	maxRetained       int
}

// sseClient 单个 SSE 客户端连接
type sseClient struct {
	learnerID string
	ch        chan sequencedEvent
	lastSeq   int64 // 客户端最后确认的序号(用于重连)
}

// sequencedEvent 带序号的事件
type sequencedEvent struct {
	Seq   int64
	Event eventbus.Event
}

// ringBuffer 环形缓冲区 -- 保留最近 N 条事件
type ringBuffer struct {
	mu     sync.Mutex
	events []retainedEvent
	head   int
	count  int
	cap    int
}

// retainedEvent 缓存的事件
type retainedEvent struct {
	Seq   int64
	Event eventbus.Event
}

// newRingBuffer 创建环形缓冲区
func newRingBuffer(capacity int) *ringBuffer {
	return &ringBuffer{
		events: make([]retainedEvent, capacity),
		cap:    capacity,
	}
}

// push 添加事件到环形缓冲
func (rb *ringBuffer) push(seq int64, event eventbus.Event) {
	rb.mu.Lock()
	defer rb.mu.Unlock()
	rb.events[rb.head] = retainedEvent{Seq: seq, Event: event}
	rb.head = (rb.head + 1) % rb.cap
	if rb.count < rb.cap {
		rb.count++
	}
}

// getSince 获取 seq > afterSeq 的事件(用于重连回放)
func (rb *ringBuffer) getSince(afterSeq int64) []retainedEvent {
	rb.mu.Lock()
	defer rb.mu.Unlock()
	result := make([]retainedEvent, 0)
	for i := 0; i < rb.count; i++ {
		idx := (rb.head - rb.count + i + rb.cap) % rb.cap
		if rb.events[idx].Seq > afterSeq {
			result = append(result, rb.events[idx])
		}
	}
	return result
}

// getRecent 获取最近 n 条事件
func (rb *ringBuffer) getRecent(n int) []retainedEvent {
	rb.mu.Lock()
	defer rb.mu.Unlock()
	if n > rb.count {
		n = rb.count
	}
	result := make([]retainedEvent, 0, n)
	for i := rb.count - n; i < rb.count; i++ {
		idx := (rb.head - rb.count + i + rb.cap) % rb.cap
		result = append(result, rb.events[idx])
	}
	return result
}

// NewEnhancedSSEManager 创建增强型 SSE 管理器
func NewEnhancedSSEManager() *EnhancedSSEManager {
	return &EnhancedSSEManager{
		clients:           make(map[string][]*sseClient),
		retainedEvents:    make(map[string]*ringBuffer),
		heartbeatInterval: 30 * time.Second,
		maxRetained:       100,
	}
}

// Register 注册新的 SSE 客户端
// lastSeq 为客户端最后确认的序号,>0 时触发重连回放
func (m *EnhancedSSEManager) Register(learnerID string, lastSeq int64) (*sseClient, []retainedEvent) {
	ch := make(chan sequencedEvent, 64)
	client := &sseClient{learnerID: learnerID, ch: ch, lastSeq: lastSeq}

	m.mu.Lock()
	m.clients[learnerID] = append(m.clients[learnerID], client)
	retained, ok := m.retainedEvents[learnerID]
	m.mu.Unlock()

	var replay []retainedEvent
	if ok && lastSeq > 0 {
		// 重连: 回放 lastSeq 之后的事件
		replay = retained.getSince(lastSeq)
		log.Printf("[SSE] reconnect: learner=%s last_seq=%d replay=%d", learnerID, lastSeq, len(replay))
	}

	return client, replay
}

// Unregister 注销 SSE 客户端
func (m *EnhancedSSEManager) Unregister(learnerID string, client *sseClient) {
	m.mu.Lock()
	defer m.mu.Unlock()
	clients := m.clients[learnerID]
	for i, c := range clients {
		if c == client {
			m.clients[learnerID] = append(clients[:i], clients[i+1:]...)
			break
		}
	}
	if len(m.clients[learnerID]) == 0 {
		delete(m.clients, learnerID)
	}
	close(client.ch)
}

// PublishEvent 发布事件到所有匹配的 SSE 客户端
// 自动附加 seq 并缓存到环形缓冲
func (m *EnhancedSSEManager) PublishEvent(event eventbus.Event) {
	seq := m.globalSequence.Add(1)

	// 缓存到环形缓冲
	m.mu.RLock()
	retained, ok := m.retainedEvents[event.LearnerID]
	m.mu.RUnlock()
	if !ok {
		retained = newRingBuffer(m.maxRetained)
		m.mu.Lock()
		m.retainedEvents[event.LearnerID] = retained
		m.mu.Unlock()
	}
	retained.push(seq, event)

	// 推送给所有客户端
	m.mu.RLock()
	clients := m.clients[event.LearnerID]
	m.mu.RUnlock()

	sent := false
	for _, client := range clients {
		if client.lastSeq > 0 && seq <= client.lastSeq {
			// 客户端已通过重连回放获取过此事件,跳过
			continue
		}
		select {
		case client.ch <- sequencedEvent{Seq: seq, Event: event}:
			sent = true
		default:
			// 客户端慢,丢弃
		}
	}
	if sent {
		log.Printf("[SSE] event delivered: seq=%d type=%s learner=%s", seq, event.Type, event.LearnerID)
	}
}

// GetHeartbeatInterval 返回心跳间隔
func (m *EnhancedSSEManager) GetHeartbeatInterval() time.Duration {
	return m.heartbeatInterval
}

// GetRecentEvents 获取学习者最近的事件(新连接时发送)
func (m *EnhancedSSEManager) GetRecentEvents(learnerID string, n int) []retainedEvent {
	m.mu.RLock()
	retained, ok := m.retainedEvents[learnerID]
	m.mu.RUnlock()
	if !ok {
		return nil
	}
	return retained.getRecent(n)
}

// HandleSSE 处理 SSE 连接(HTTP handler)
func (m *EnhancedSSEManager) HandleSSE(w http.ResponseWriter, r *http.Request) {
	learnerID := r.PathValue("learnerID")
	if learnerID == "" {
		http.Error(w, "learnerID required", http.StatusBadRequest)
		return
	}

	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "Streaming not supported", http.StatusInternalServerError)
		return
	}

	// 解析 Last-Event-ID (重连)
	lastSeq := int64(0)
	if lastEventID := r.Header.Get("Last-Event-ID"); lastEventID != "" {
		// 支持 "seq: 42" 或纯数字 "42"
		cleaned := strings.TrimPrefix(lastEventID, "seq:")
		cleaned = strings.TrimSpace(cleaned)
		var seq int64
		if _, err := fmt.Sscanf(cleaned, "%d", &seq); err == nil {
			lastSeq = seq
		}
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Expose-Headers", "Last-Event-ID")

	client, replay := m.Register(learnerID, lastSeq)
	defer m.Unregister(learnerID, client)

	// 发送重连回放或最近历史
	if len(replay) > 0 {
		for _, evt := range replay {
			m.writeEvent(w, flusher, evt.Seq, evt.Event)
		}
	} else if lastSeq == 0 {
		// 新连接: 发送最近 10 条
		recent := m.GetRecentEvents(learnerID, 10)
		for _, evt := range recent {
			m.writeEvent(w, flusher, evt.Seq, evt.Event)
		}
	}
	flusher.Flush()

	// 主循环: 实时事件 + 心跳
	ticker := time.NewTicker(m.heartbeatInterval)
	defer ticker.Stop()

	for {
		select {
		case <-r.Context().Done():
			return
		case se, ok := <-client.ch:
			if !ok {
				return
			}
			m.writeEvent(w, flusher, se.Seq, se.Event)
			flusher.Flush()
		case <-ticker.C:
			// 发送心跳注释
			fmt.Fprintf(w, ":heartbeat\n\n")
			flusher.Flush()
		}
	}
}

// writeEvent 写入单个 SSE 事件
func (m *EnhancedSSEManager) writeEvent(w http.ResponseWriter, flusher http.Flusher, seq int64, event eventbus.Event) {
	// 构造带 seq 的事件数据
	eventWithSeq := map[string]interface{}{
		"seq": seq,
		"id": event.ID,
		"type": event.Type,
		"source": event.Source,
		"learner_id": event.LearnerID,
		"timestamp": event.Timestamp,
		"correlation_id": event.CorrelationID,
		"data": event.Data,
	}
	data, _ := json.Marshal(eventWithSeq)
	fmt.Fprintf(w, "seq: %d\n", seq)
	fmt.Fprintf(w, "event: %s\n", event.Type)
	fmt.Fprintf(w, "data: %s\n\n", data)
}
