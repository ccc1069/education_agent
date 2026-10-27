package api

import (
	"encoding/json"
	"log"
	"net/http"
	"sync"
	"time"

	"github.com/gorilla/websocket"

	"multi-agent-education/golang/internal/auth"
	"multi-agent-education/golang/internal/eventbus"
)

// WebSocket 协议常量
const (
	wsReadLimit   = 64 * 1024  // 64KB 消息上限
	wsPongWait    = 10 * time.Second // 等待 pong 超时
	wsPingPeriod  = 60 * time.Second // 心跳 ping 间隔
	wsWriteWait   = 10 * time.Second // 写超时
)

// wsClient 单个 WebSocket 连接
type wsClient struct {
	learnerID string
	conn      *websocket.Conn
	send      chan []byte
	manager   *WebSocketManager
	mu        sync.Mutex
	closed    bool // 标记 send 通道是否已关闭
}

// WebSocketManager WebSocket 连接管理器
//
// 面试要点:
// - gorilla/websocket 行业标准库
// - 心跳机制: 60s ping / 10s pong 超时
// - 单连接驱逐: 同一 learnerID 新连接踢掉旧连接 (4002)
// - 事件推送: 订阅 EventBus 实时推送
// - 重连回放: 从 history 获取断线期间事件
type WebSocketManager struct {
	upgrader    websocket.Upgrader
	clients     map[string]*wsClient // learnerID -> client
	mu          sync.RWMutex
	bus         *eventbus.EventBus
	jwtSecret   auth.Key
	sequenceNum uint64
}

// NewWebSocketManager 创建 WebSocket 管理器
func NewWebSocketManager(bus *eventbus.EventBus, jwtSecret auth.Key) *WebSocketManager {
	mgr := &WebSocketManager{
		upgrader: websocket.Upgrader{
			ReadBufferSize:  1024,
			WriteBufferSize: 1024,
			CheckOrigin:     func(r *http.Request) bool { return true }, // 开发环境允许所有来源
		},
		clients:   make(map[string]*wsClient),
		bus:       bus,
		jwtSecret: jwtSecret,
	}

	// 订阅事件总线,广播给所有 WebSocket 客户端
	mgr.subscribeEvents()

	return mgr
}

// subscribeEvents 订阅事件总线
func (m *WebSocketManager) subscribeEvents() {
	allEventTypes := []eventbus.EventType{
		eventbus.StudentSubmission, eventbus.StudentQuestion, eventbus.StudentMessage,
		eventbus.AssessmentComplete, eventbus.MasteryUpdated, eventbus.WeaknessDetected,
		eventbus.TeachingResponse, eventbus.HintResponse, eventbus.DifficultyAdjusted,
		eventbus.PathUpdated, eventbus.ReviewScheduled, eventbus.NextTopic,
		eventbus.EngagementAlert, eventbus.Encouragement, eventbus.PaceAdjustment,
		eventbus.TeachingCriticized, eventbus.DebateConsensus,
		eventbus.NotificationSent, eventbus.VisionAnalyzed,
	}
	for _, et := range allEventTypes {
		et := et
		m.bus.Subscribe(et, func(event eventbus.Event) {
			m.broadcastEvent(event)
		})
	}
}

// HandleWS WebSocket 连接处理
// GET /ws/{learnerID}?token=JWT
func (m *WebSocketManager) HandleWS(w http.ResponseWriter, r *http.Request) {
	learnerID := r.PathValue("learnerID")
	if learnerID == "" {
		http.Error(w, `{"error":"learnerID required"}`, http.StatusBadRequest)
		return
	}

	// JWT 认证 (query param token)
	token := r.URL.Query().Get("token")
	if token == "" {
		// 尝试从 Authorization header 获取
		token = extractBearerTokenWS(r)
	}
	if token == "" {
		http.Error(w, `{"error":"token required"}`, http.StatusUnauthorized)
		return
	}

	claims, err := auth.ParseToken(m.jwtSecret, token)
	if err != nil {
		http.Error(w, `{"error":"invalid token"}`, http.StatusUnauthorized)
		return
	}
	// 仅允许 access token
	if claims.TokenType != "access" && claims.TokenType != "" {
		http.Error(w, `{"error":"invalid token type"}`, http.StatusUnauthorized)
		return
	}

	// 校验 learnerID 与 token 匹配 (除非 admin)
	if claims.UserID != learnerID && claims.Role != string(auth.RoleAdmin) {
		http.Error(w, `{"error":"learnerID mismatch"}`, http.StatusForbidden)
		return
	}

	// 升级连接
	conn, err := m.upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("[WS] upgrade error: %v", err)
		return
	}

	// 单连接驱逐: 关闭旧连接
	m.mu.Lock()
	oldClient, exists := m.clients[learnerID]
	m.mu.Unlock()

	if exists {
		oldClient.markClosed()
		oldClient.conn.Close()
		log.Printf("[WS] evicted old connection for learner=%s", learnerID)
	}

	client := &wsClient{
		learnerID: learnerID,
		conn:      conn,
		send:      make(chan []byte, 256),
		manager:   m,
	}

	m.mu.Lock()
	m.clients[learnerID] = client
	m.mu.Unlock()

	// 发送连接成功消息
	client.sendJSON(map[string]interface{}{
		"type":        "connected",
		"learner_id":  learnerID,
		"server_time": time.Now().Unix(),
	})

	// 启动读写 goroutine
	go client.writePump()
	go client.readPump()
}

// broadcastEvent 广播事件给相关客户端
func (m *WebSocketManager) broadcastEvent(event eventbus.Event) {
	msg := map[string]interface{}{
		"type":       "event",
		"event_type": string(event.Type),
		"source":     event.Source,
		"data":       event.Data,
		"timestamp":  event.Timestamp.Unix(),
	}

	msgBytes, err := json.Marshal(msg)
	if err != nil {
		return
	}

	m.mu.RLock()
	defer m.mu.RUnlock()

	for learnerID, client := range m.clients {
		// 仅推送给相关学习者
		if event.LearnerID != "" && event.LearnerID != learnerID {
			continue
		}
		select {
		case client.send <- msgBytes:
		default:
			// 发送缓冲区满,丢弃
		}
	}
}

// writePump 写 goroutine (发送消息到客户端)
func (c *wsClient) writePump() {
	ticker := time.NewTicker(wsPingPeriod)
	defer func() {
		ticker.Stop()
		c.conn.Close()
	}()

	for {
		select {
		case message, ok := <-c.send:
			c.conn.SetWriteDeadline(time.Now().Add(wsWriteWait))
			if !ok {
				// channel 关闭
				c.conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}

			w, err := c.conn.NextWriter(websocket.TextMessage)
			if err != nil {
				return
			}
			w.Write(message)

			// 批量发送缓冲区的消息
			n := len(c.send)
			for i := 0; i < n; i++ {
				w.Write([]byte{'\n'})
				w.Write(<-c.send)
			}

			if err := w.Close(); err != nil {
				return
			}

		case <-ticker.C:
			// 心跳 ping
			c.conn.SetWriteDeadline(time.Now().Add(wsWriteWait))
			if err := c.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}

// readPump 读 goroutine (接收客户端消息)
func (c *wsClient) readPump() {
	defer func() {
		c.manager.unregister(c.learnerID)
		c.conn.Close()
	}()

	c.conn.SetReadLimit(wsReadLimit)
	c.conn.SetReadDeadline(time.Now().Add(wsPongWait))
	c.conn.SetPongHandler(func(string) error {
		c.conn.SetReadDeadline(time.Now().Add(wsPongWait))
		return nil
	})

	for {
		_, message, err := c.conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err,
				websocket.CloseGoingAway, websocket.CloseAbnormalClosure,
				websocket.CloseNormalClosure) {
				log.Printf("[WS] read error from %s: %v", c.learnerID, err)
			}
			break
		}

		// 处理客户端消息
		c.handleClientMessage(message)
	}
}

// handleClientMessage 处理客户端发来的消息
func (c *wsClient) handleClientMessage(data []byte) {
	var msg struct {
		Action  string                 `json:"action"`
		Payload map[string]interface{} `json:"payload"`
	}
	if err := json.Unmarshal(data, &msg); err != nil {
		c.sendJSON(map[string]interface{}{"type": "error", "error": "invalid JSON"})
		return
	}

	switch msg.Action {
	case "pong":
		// 客户端心跳响应,已由 SetPongHandler 处理

	case "submit":
		// 学生提交答题
		c.manager.bus.Publish(eventbus.Event{
			Type:      eventbus.StudentSubmission,
			Source:    "ws",
			LearnerID: c.learnerID,
			Data:      msg.Payload,
		})

	case "question":
		// 学生提问
		c.manager.bus.Publish(eventbus.Event{
			Type:      eventbus.StudentQuestion,
			Source:    "ws",
			LearnerID: c.learnerID,
			Data:      msg.Payload,
		})

	case "message":
		// 学生消息
		c.manager.bus.Publish(eventbus.Event{
			Type:      eventbus.StudentMessage,
			Source:    "ws",
			LearnerID: c.learnerID,
			Data:      msg.Payload,
		})

	case "reconnect":
		// 重连回放: 返回断线期间的事件历史
		if lastSeq, ok := msg.Payload["last_seq"].(float64); ok {
			history := c.manager.bus.GetHistory(c.learnerID, 50)
			c.sendJSON(map[string]interface{}{
				"type":    "replay",
				"last_seq": uint64(lastSeq),
				"events":  history,
			})
		}

	default:
		c.sendJSON(map[string]interface{}{"type": "error", "error": "unknown action: " + msg.Action})
	}
}

// sendJSON 发送 JSON 消息
func (c *wsClient) sendJSON(data interface{}) {
	c.mu.Lock()
	defer c.mu.Unlock()

	msg, err := json.Marshal(data)
	if err != nil {
		return
	}

	select {
	case c.send <- msg:
	default:
		// 缓冲区满
	}
}

// unregister 注销客户端 (幂等)
func (m *WebSocketManager) unregister(learnerID string) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if client, ok := m.clients[learnerID]; ok {
		client.markClosed()
		delete(m.clients, learnerID)
		log.Printf("[WS] unregistered learner=%s", learnerID)
	}
}

// markClosed 标记并关闭 send 通道 (幂等)
func (c *wsClient) markClosed() {
	c.mu.Lock()
	defer c.mu.Unlock()
	if !c.closed {
		c.closed = true
		close(c.send)
	}
}

// ClientCount 返回当前连接数
func (m *WebSocketManager) ClientCount() int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return len(m.clients)
}

// extractBearerTokenWS 从请求头提取 Bearer token
func extractBearerTokenWS(r *http.Request) string {
	authHeader := r.Header.Get("Authorization")
	if authHeader == "" {
		return ""
	}
	const prefix = "Bearer "
	if len(authHeader) > len(prefix) && authHeader[:len(prefix)] == prefix {
		return authHeader[len(prefix):]
	}
	return ""
}
