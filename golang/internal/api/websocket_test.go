package api

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"

	"multi-agent-education/golang/internal/auth"
	"multi-agent-education/golang/internal/eventbus"
)

// wsTestHandler 从 URL 路径提取 learnerID 并调用 HandleWS
// (httptest.NewServer 不自动填充 PathValue)
func wsTestHandler(mgr *WebSocketManager) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		// 从路径 /ws/{learnerID} 提取 learnerID
		path := strings.TrimPrefix(r.URL.Path, "/ws/")
		if path != "" && !strings.Contains(path, "/") {
			r.SetPathValue("learnerID", path)
		}
		mgr.HandleWS(w, r)
	}
}

func TestWebSocketManager_HandleWS_NoToken(t *testing.T) {
	bus := eventbus.New()
	secret := auth.Key([]byte("test-secret-32bytes-for-test-only!"))
	mgr := NewWebSocketManager(bus, secret)

	req := httptest.NewRequest("GET", "/ws/learner-001", nil)
	req.SetPathValue("learnerID", "learner-001")
	w := httptest.NewRecorder()

	mgr.HandleWS(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", w.Code)
	}
}

func TestWebSocketManager_HandleWS_InvalidLearnerID(t *testing.T) {
	bus := eventbus.New()
	secret := auth.Key([]byte("test-secret-32bytes-for-test-only!"))
	mgr := NewWebSocketManager(bus, secret)

	// 无 learnerID 的请求
	req := httptest.NewRequest("GET", "/ws/", nil)
	w := httptest.NewRecorder()

	mgr.HandleWS(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

func TestWebSocketManager_HandleWS_TokenMismatch(t *testing.T) {
	bus := eventbus.New()
	secret := auth.Key([]byte("test-secret-32bytes-for-test-only!"))
	mgr := NewWebSocketManager(bus, secret)

	// 为 user-002 生成 token,但请求 learner-001
	token, err := auth.CreateAccessToken(secret, "user-002", "user002@test.com", "student", "default", "user-002")
	if err != nil {
		t.Fatalf("CreateAccessToken failed: %v", err)
	}

	req := httptest.NewRequest("GET", "/ws/learner-001?token="+token, nil)
	req.SetPathValue("learnerID", "learner-001")
	w := httptest.NewRecorder()

	mgr.HandleWS(w, req)

	if w.Code != http.StatusForbidden {
		t.Fatalf("expected 403, got %d", w.Code)
	}
}

func TestWebSocketManager_HandleWS_Success(t *testing.T) {
	bus := eventbus.New()
	secret := auth.Key([]byte("test-secret-32bytes-for-test-only!"))
	mgr := NewWebSocketManager(bus, secret)

	// 启动测试 WebSocket 服务器
	server := httptest.NewServer(wsTestHandler(mgr))
	defer server.Close()

	// 为 learner-001 生成 token
	token, err := auth.CreateAccessToken(secret, "learner-001", "learner@test.com", "student", "default", "learner-001")
	if err != nil {
		t.Fatalf("CreateAccessToken failed: %v", err)
	}

	// 连接 WebSocket
	wsURL := "ws" + strings.TrimPrefix(server.URL, "http") + "/ws/learner-001?token=" + token
	conn, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("WebSocket dial failed: %v", err)
	}
	defer conn.Close()

	// 设置读取超时
	conn.SetReadDeadline(time.Now().Add(2 * time.Second))

	// 读取连接成功消息
	var msg map[string]interface{}
	if err := conn.ReadJSON(&msg); err != nil {
		t.Fatalf("ReadJSON failed: %v", err)
	}
	if msg["type"] != "connected" {
		t.Fatalf("expected type=connected, got %v", msg["type"])
	}
	if msg["learner_id"] != "learner-001" {
		t.Fatalf("expected learner-001, got %v", msg["learner_id"])
	}

	// 验证连接数
	if mgr.ClientCount() != 1 {
		t.Fatalf("expected 1 client, got %d", mgr.ClientCount())
	}
}

func TestWebSocketManager_SingleConnectionEviction(t *testing.T) {
	bus := eventbus.New()
	secret := auth.Key([]byte("test-secret-32bytes-for-test-only!"))
	mgr := NewWebSocketManager(bus, secret)

	server := httptest.NewServer(wsTestHandler(mgr))
	defer server.Close()

	token, err := auth.CreateAccessToken(secret, "learner-001", "learner@test.com", "student", "default", "learner-001")
	if err != nil {
		t.Fatalf("CreateAccessToken failed: %v", err)
	}

	wsURL := "ws" + strings.TrimPrefix(server.URL, "http") + "/ws/learner-001?token=" + token

	// 第一个连接
	conn1, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("First dial failed: %v", err)
	}
	defer conn1.Close()

	conn1.SetReadDeadline(time.Now().Add(2 * time.Second))
	var msg map[string]interface{}
	conn1.ReadJSON(&msg) // 读取 connected 消息

	// 第二个连接 (应驱逐第一个)
	conn2, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("Second dial failed: %v", err)
	}
	defer conn2.Close()

	conn2.SetReadDeadline(time.Now().Add(2 * time.Second))
	conn2.ReadJSON(&msg) // 读取 connected 消息

	// 验证仍然只有 1 个连接
	if mgr.ClientCount() != 1 {
		t.Fatalf("expected 1 client after eviction, got %d", mgr.ClientCount())
	}
}

func TestWebSocketManager_ClientMessage(t *testing.T) {
	bus := eventbus.New()
	secret := auth.Key([]byte("test-secret-32bytes-for-test-only!"))
	mgr := NewWebSocketManager(bus, secret)

	server := httptest.NewServer(wsTestHandler(mgr))
	defer server.Close()

	token, err := auth.CreateAccessToken(secret, "learner-001", "learner@test.com", "student", "default", "learner-001")
	if err != nil {
		t.Fatalf("CreateAccessToken failed: %v", err)
	}

	wsURL := "ws" + strings.TrimPrefix(server.URL, "http") + "/ws/learner-001?token=" + token
	conn, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("Dial failed: %v", err)
	}
	defer conn.Close()

	conn.SetReadDeadline(time.Now().Add(2 * time.Second))
	var msg map[string]interface{}
	conn.ReadJSON(&msg) // 读取 connected 消息

	// 发送 submit 消息
	submitMsg := map[string]interface{}{
		"action": "submit",
		"payload": map[string]interface{}{
			"knowledge_id": "kp-001",
			"is_correct":   true,
		},
	}
	if err := conn.WriteJSON(submitMsg); err != nil {
		t.Fatalf("WriteJSON failed: %v", err)
	}

	// 发送 pong 消息
	pongMsg := map[string]interface{}{"action": "pong"}
	if err := conn.WriteJSON(pongMsg); err != nil {
		t.Fatalf("WriteJSON pong failed: %v", err)
	}

	// 发送 reconnect 消息
	reconnectMsg := map[string]interface{}{
		"action": "reconnect",
		"payload": map[string]interface{}{
			"last_seq": float64(0),
		},
	}
	if err := conn.WriteJSON(reconnectMsg); err != nil {
		t.Fatalf("WriteJSON reconnect failed: %v", err)
	}

	// 读取 replay 响应 (可能先收到 event 消息,需跳过)
	conn.SetReadDeadline(time.Now().Add(3 * time.Second))
	var replay map[string]interface{}
	for {
		if err := conn.ReadJSON(&replay); err != nil {
			t.Fatalf("ReadJSON replay failed: %v", err)
		}
		if replay["type"] == "replay" {
			break
		}
	}
}

func TestWebSocketManager_UnknownAction(t *testing.T) {
	bus := eventbus.New()
	secret := auth.Key([]byte("test-secret-32bytes-for-test-only!"))
	mgr := NewWebSocketManager(bus, secret)

	server := httptest.NewServer(wsTestHandler(mgr))
	defer server.Close()

	token, err := auth.CreateAccessToken(secret, "learner-001", "learner@test.com", "student", "default", "learner-001")
	if err != nil {
		t.Fatalf("CreateAccessToken failed: %v", err)
	}

	wsURL := "ws" + strings.TrimPrefix(server.URL, "http") + "/ws/learner-001?token=" + token
	conn, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		t.Fatalf("Dial failed: %v", err)
	}
	defer conn.Close()

	conn.SetReadDeadline(time.Now().Add(2 * time.Second))
	var msg map[string]interface{}
	conn.ReadJSON(&msg) // 读取 connected 消息

	// 发送未知 action
	unknownMsg := map[string]interface{}{"action": "unknown_action"}
	if err := conn.WriteJSON(unknownMsg); err != nil {
		t.Fatalf("WriteJSON failed: %v", err)
	}

	// 读取错误响应
	conn.SetReadDeadline(time.Now().Add(2 * time.Second))
	var errMsg map[string]interface{}
	if err := conn.ReadJSON(&errMsg); err != nil {
		t.Fatalf("ReadJSON error failed: %v", err)
	}
	if errMsg["type"] != "error" {
		t.Fatalf("expected type=error, got %v", errMsg["type"])
	}
}
