package api

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"multi-agent-education/golang/internal/eventbus"
)

// ─── 环形缓冲区测试 ───

func TestRingBuffer_PushAndRecent(t *testing.T) {
	rb := newRingBuffer(3)

	rb.push(1, eventbus.Event{Type: "a"})
	rb.push(2, eventbus.Event{Type: "b"})
	rb.push(3, eventbus.Event{Type: "c"})

	recent := rb.getRecent(2)
	if len(recent) != 2 {
		t.Errorf("expected 2 recent events, got %d", len(recent))
	}
	if recent[0].Seq != 2 || recent[1].Seq != 3 {
		t.Errorf("expected seq [2,3], got [%d,%d]", recent[0].Seq, recent[1].Seq)
	}
}

func TestRingBuffer_Overflow(t *testing.T) {
	rb := newRingBuffer(2)

	rb.push(1, eventbus.Event{Type: "a"})
	rb.push(2, eventbus.Event{Type: "b"})
	rb.push(3, eventbus.Event{Type: "c"}) // 溢出,丢弃最旧的

	recent := rb.getRecent(10)
	if len(recent) != 2 {
		t.Errorf("expected 2 events (capacity), got %d", len(recent))
	}
	// 应该保留 seq 2 和 3
	if recent[0].Seq != 2 || recent[1].Seq != 3 {
		t.Errorf("expected seq [2,3], got [%d,%d]", recent[0].Seq, recent[1].Seq)
	}
}

func TestRingBuffer_GetSince(t *testing.T) {
	rb := newRingBuffer(10)

	for i := int64(1); i <= 5; i++ {
		rb.push(i, eventbus.Event{Type: eventbus.EventType(fmt.Sprintf("e%d", i))})
	}

	since := rb.getSince(3)
	if len(since) != 2 {
		t.Errorf("expected 2 events after seq 3, got %d", len(since))
	}
	if since[0].Seq != 4 || since[1].Seq != 5 {
		t.Errorf("expected seq [4,5], got [%d,%d]", since[0].Seq, since[1].Seq)
	}
}

func TestRingBuffer_GetSince_Empty(t *testing.T) {
	rb := newRingBuffer(10)

	rb.push(1, eventbus.Event{Type: "a"})
	rb.push(2, eventbus.Event{Type: "b"})

	since := rb.getSince(100) // 超过所有 seq
	if len(since) != 0 {
		t.Errorf("expected 0 events, got %d", len(since))
	}
}

// ─── EnhancedSSEManager 测试 ───

func TestSSEManager_RegisterAndPublish(t *testing.T) {
	mgr := NewEnhancedSSEManager()

	// 发布事件
	mgr.PublishEvent(eventbus.Event{
		Type: eventbus.TeachingResponse, Source: "TutorAgent",
		LearnerID: "learner1",
		Data:      map[string]interface{}{"response": "hello"},
	})

	// 注册客户端
	client, replay := mgr.Register("learner1", 0)
	if len(replay) != 0 {
		t.Errorf("new connection should have no replay, got %d", len(replay))
	}

	// 验证事件已缓存
	recent := mgr.GetRecentEvents("learner1", 10)
	if len(recent) != 1 {
		t.Errorf("expected 1 cached event, got %d", len(recent))
	}

	// 清理
	mgr.Unregister("learner1", client)
}

func TestSSEManager_ReconnectReplay(t *testing.T) {
	mgr := NewEnhancedSSEManager()

	// 发布 5 个事件
	for i := 0; i < 5; i++ {
		mgr.PublishEvent(eventbus.Event{
			Type: eventbus.TeachingResponse, Source: "TutorAgent",
			LearnerID: "learner1",
			Data:      map[string]interface{}{"i": i},
		})
	}

	// 模拟重连: lastSeq=3,应回放 seq 4,5
	client, replay := mgr.Register("learner1", 3)
	if len(replay) != 2 {
		t.Errorf("expected 2 replay events, got %d", len(replay))
	}
	if len(replay) == 2 {
		if replay[0].Seq != 4 || replay[1].Seq != 5 {
			t.Errorf("expected replay seq [4,5], got [%d,%d]", replay[0].Seq, replay[1].Seq)
		}
	}

	mgr.Unregister("learner1", client)
}

func TestSSEManager_GlobalSequence(t *testing.T) {
	mgr := NewEnhancedSSEManager()

	// 发布多个事件,验证序号单调递增
	for i := 0; i < 10; i++ {
		mgr.PublishEvent(eventbus.Event{
			Type: eventbus.TeachingResponse, Source: "TutorAgent",
			LearnerID: "learner1",
		})
	}

	recent := mgr.GetRecentEvents("learner1", 10)
	if len(recent) != 10 {
		t.Fatalf("expected 10 events, got %d", len(recent))
	}

	// 验证单调递增
	for i := 1; i < len(recent); i++ {
		if recent[i].Seq <= recent[i-1].Seq {
			t.Errorf("seq not monotonic: %d <= %d", recent[i].Seq, recent[i-1].Seq)
		}
	}
}

func TestSSEManager_MultipleClients(t *testing.T) {
	mgr := NewEnhancedSSEManager()

	client1, _ := mgr.Register("learner1", 0)
	client2, _ := mgr.Register("learner1", 0)

	mgr.PublishEvent(eventbus.Event{
		Type: eventbus.TeachingResponse, Source: "TutorAgent",
		LearnerID: "learner1",
		Data:      map[string]interface{}{"msg": "broadcast"},
	})

	// 两个客户端都应收到
	select {
	case se := <-client1.ch:
		if se.Event.Data["msg"] != "broadcast" {
			t.Errorf("client1 got wrong data: %v", se.Event.Data)
		}
	case <-time.After(time.Second):
		t.Error("client1 did not receive event")
	}

	select {
	case se := <-client2.ch:
		if se.Event.Data["msg"] != "broadcast" {
			t.Errorf("client2 got wrong data: %v", se.Event.Data)
		}
	case <-time.After(time.Second):
		t.Error("client2 did not receive event")
	}

	mgr.Unregister("learner1", client1)
	mgr.Unregister("learner1", client2)
}

func TestSSEManager_RetainedBufferCapacity(t *testing.T) {
	mgr := NewEnhancedSSEManager()

	// 发布超过 100 条事件
	for i := 0; i < 150; i++ {
		mgr.PublishEvent(eventbus.Event{
			Type: eventbus.TeachingResponse, Source: "TutorAgent",
			LearnerID: "learner1",
		})
	}

	recent := mgr.GetRecentEvents("learner1", 200)
	if len(recent) != 100 {
		t.Errorf("expected max 100 retained events, got %d", len(recent))
	}

	// 验证保留的是最新的 100 条 (seq 51-150)
	if recent[0].Seq != 51 || recent[99].Seq != 150 {
		t.Errorf("expected seq range [51,150], got [%d,%d]", recent[0].Seq, recent[99].Seq)
	}
}

// ─── HTTP SSE 集成测试 ───

func TestSSEHandler_StreamEvents(t *testing.T) {
	bus := eventbus.New()
	mgr := NewEnhancedSSEManager()

	// 订阅事件
	bus.Subscribe(eventbus.TeachingResponse, func(e eventbus.Event) {
		mgr.PublishEvent(e)
	})

	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/v1/stream/{learnerID}", func(w http.ResponseWriter, r *http.Request) {
		mgr.HandleSSE(w, r)
	})

	server := httptest.NewServer(mux)
	defer server.Close()

	// 发起 SSE 连接
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	req, _ := http.NewRequestWithContext(ctx, "GET", server.URL+"/api/v1/stream/learner1", nil)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("failed to connect: %v", err)
	}
	defer resp.Body.Close()

	// 验证响应头
	if resp.Header.Get("Content-Type") != "text/event-stream" {
		t.Errorf("expected Content-Type text/event-stream, got %s", resp.Header.Get("Content-Type"))
	}

	// 异步发布事件
	go func() {
		time.Sleep(100 * time.Millisecond)
		bus.Publish(eventbus.Event{
			Type: eventbus.TeachingResponse, Source: "TutorAgent",
			LearnerID: "learner1",
			Data:      map[string]interface{}{"response": "hello"},
		})
	}()

	// 读取 SSE 响应
	reader := bufio.NewReader(resp.Body)
	line, err := reader.ReadString('\n')
	if err != nil {
		t.Fatalf("failed to read SSE: %v", err)
	}

	// 第一行应该是 seq: 或 event: 或 data:
	if !strings.Contains(line, "seq:") && !strings.Contains(line, "event:") && !strings.Contains(line, "data:") {
		t.Errorf("unexpected first SSE line: %s", line)
	}
}

func TestSSEHandler_ReconnectWithLastEventID(t *testing.T) {
	mgr := NewEnhancedSSEManager()

	// 预发布 5 个事件
	for i := 0; i < 5; i++ {
		mgr.PublishEvent(eventbus.Event{
			Type: eventbus.TeachingResponse, Source: "TutorAgent",
			LearnerID: "learner1",
			Data:      map[string]interface{}{"i": i},
		})
	}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/v1/stream/{learnerID}", func(w http.ResponseWriter, r *http.Request) {
		mgr.HandleSSE(w, r)
	})

	server := httptest.NewServer(mux)
	defer server.Close()

	// 重连: Last-Event-ID: 3
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	req, _ := http.NewRequestWithContext(ctx, "GET", server.URL+"/api/v1/stream/learner1", nil)
	req.Header.Set("Last-Event-ID", "3")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("failed to connect: %v", err)
	}
	defer resp.Body.Close()

	// 读取响应,验证只收到 seq 4,5
	reader := bufio.NewReader(resp.Body)
	var receivedSeqs []int64
	for {
		line, err := reader.ReadString('\n')
		if err != nil {
			break
		}
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "seq:") {
			var seq int64
			fmt.Sscanf(line, "seq: %d", &seq)
			receivedSeqs = append(receivedSeqs, seq)
		}
	}

	// 应该只收到 2 个事件 (seq 4,5)
	if len(receivedSeqs) != 2 {
		t.Errorf("expected 2 replay events, got %d (seqs=%v)", len(receivedSeqs), receivedSeqs)
	}
}

func TestSSEHandler_Heartbeat(t *testing.T) {
	mgr := NewEnhancedSSEManager()
	// 缩短心跳间隔以便测试
	mgr.heartbeatInterval = 200 * time.Millisecond

	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/v1/stream/{learnerID}", func(w http.ResponseWriter, r *http.Request) {
		mgr.HandleSSE(w, r)
	})

	server := httptest.NewServer(mux)
	defer server.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 1*time.Second)
	defer cancel()

	req, _ := http.NewRequestWithContext(ctx, "GET", server.URL+"/api/v1/stream/learner1", nil)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("failed to connect: %v", err)
	}
	defer resp.Body.Close()

	reader := bufio.NewReader(resp.Body)
	heartbeatCount := 0
	done := time.After(700 * time.Millisecond)

loop:
	for {
		select {
		case <-done:
			break loop
		default:
			line, err := reader.ReadString('\n')
			if err != nil {
				break loop
			}
			if strings.TrimSpace(line) == ":heartbeat" {
				heartbeatCount++
			}
		}
	}

	if heartbeatCount < 2 {
		t.Errorf("expected at least 2 heartbeats in 700ms, got %d", heartbeatCount)
	}
}

func TestSSEHandler_EventDataFormat(t *testing.T) {
	mgr := NewEnhancedSSEManager()

	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/v1/stream/{learnerID}", func(w http.ResponseWriter, r *http.Request) {
		mgr.HandleSSE(w, r)
	})

	server := httptest.NewServer(mux)
	defer server.Close()

	// 发布一个事件
	mgr.PublishEvent(eventbus.Event{
		Type: eventbus.TeachingResponse, Source: "TutorAgent",
		LearnerID: "learner1",
		Data:      map[string]interface{}{"response": "test"},
	})

	// 新连接应收到最近事件
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	req, _ := http.NewRequestWithContext(ctx, "GET", server.URL+"/api/v1/stream/learner1", nil)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("failed to connect: %v", err)
	}
	defer resp.Body.Close()

	reader := bufio.NewReader(resp.Body)
	var dataLines []string
	for i := 0; i < 5; i++ {
		line, err := reader.ReadString('\n')
		if err != nil {
			break
		}
		if strings.HasPrefix(line, "data:") {
			dataLines = append(dataLines, strings.TrimPrefix(line, "data:"))
		}
	}

	if len(dataLines) == 0 {
		t.Fatal("expected at least one data line")
	}

	// 验证 data 是合法 JSON 且包含 seq 字段
	var parsed map[string]interface{}
	if err := json.Unmarshal([]byte(dataLines[0]), &parsed); err != nil {
		t.Fatalf("data is not valid JSON: %v", err)
	}
	if _, ok := parsed["seq"]; !ok {
		t.Error("expected 'seq' field in event data")
	}
	if _, ok := parsed["type"]; !ok {
		t.Error("expected 'type' field in event data")
	}
}

// ─── 并发安全测试 ───

func TestSSEManager_ConcurrentPublishAndRegister(t *testing.T) {
	mgr := NewEnhancedSSEManager()
	var wg sync.WaitGroup

	// 并发发布
	wg.Add(1)
	go func() {
		defer wg.Done()
		for i := 0; i < 100; i++ {
			mgr.PublishEvent(eventbus.Event{
				Type: eventbus.TeachingResponse, Source: "TutorAgent",
				LearnerID: "learner1",
			})
		}
	}()

	// 并发注册
	wg.Add(1)
	go func() {
		defer wg.Done()
		for i := 0; i < 10; i++ {
			client, _ := mgr.Register("learner1", 0)
			time.Sleep(5 * time.Millisecond)
			mgr.Unregister("learner1", client)
		}
	}()

	wg.Wait()

	// 验证最终状态
	recent := mgr.GetRecentEvents("learner1", 200)
	if len(recent) != 100 {
		t.Errorf("expected 100 events, got %d", len(recent))
	}
}
