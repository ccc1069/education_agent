package com.edu.agent.controller;

import com.edu.agent.core.AgentEvent;
import com.edu.agent.core.EventHistoryService;
import com.edu.agent.core.EventType;
import com.edu.agent.security.JwtAuthenticatingInterceptor;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.io.IOException;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * WebSocket 端点 -- 实时双向通信(JWT 鉴权 + 心跳 + 单连接 + 优雅关闭 + 重连事件重放)。
 *
 * <p>对齐 Python api/websocket.py + P1#10 WebSocket 健壮性:
 * <ul>
 *   <li>握手阶段由 JwtAuthenticatingInterceptor 校验 token</li>
 *   <li>心跳: 60s 无消息发 ping,10s 内无 pong 则断开(4001)</li>
 *   <li>单用户单连接: 同 learnerId 新连接踢掉旧连接(4002)</li>
 *   <li>优雅关闭: 服务端 shutdown 时向所有连接发 1001 going_away</li>
 *   <li>消息序号: 每条出站事件带 sequence,客户端可检测丢包</li>
 *   <li>ACK: 客户端发 {"action":"ack","seq":N} 确认收到</li>
 *   <li>重连重放: 客户端带 last_seq 重连,服务端重发 [last_seq+1, 当前] 区间事件</li>
 * </ul>
 *
 * <p>协议:
 * <pre>
 *   入站: {"action": "submit|question|message|pong|ack", "seq": N, "last_seq": M, ...}
 *   出站: {"type": "event|error|ping|ack", "seq": N, ...}
 * </pre>
 */
@Component
public class EduWebSocketHandler extends TextWebSocketHandler {

    /** 心跳超时(秒) -- 60s 无消息则发 ping。 */
    private static final int RECEIVE_TIMEOUT_SECONDS = 60;
    /** pong 超时(秒) -- ping 后 10s 无响应则断开。 */
    private static final int PONG_TIMEOUT_SECONDS = 10;
    /** 每个 learner 保留的最近事件数(用于重连重放)。 */
    private static final int RETAINED_EVENTS_PER_LEARNER = 100;

    /** 关闭码: 心跳超时。 */
    public static final int CODE_HEARTBEAT_TIMEOUT = 4001;
    /** 关闭码: 重复连接。 */
    public static final int CODE_DUPLICATE_CONNECTION = 4002;
    /** 关闭码: 服务端关闭。 */
    public static final int CODE_SERVER_SHUTDOWN = 1001;

    private static final Logger log = LoggerFactory.getLogger(EduWebSocketHandler.class);

    private final ApplicationEventPublisher publisher;
    private final EventHistoryService historyService;
    private final com.edu.agent.service.LearnerModelService learnerModelService;
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread t = new Thread(r, "ws-heartbeat");
        t.setDaemon(true);
        return t;
    });

    /** learnerId -> session(单用户单连接)。 */
    private final Map<String, WebSocketSession> sessions = new ConcurrentHashMap<>();
    /** session -> 最后活跃时间。 */
    private final Map<String, Long> lastActivity = new ConcurrentHashMap<>();
    /** session -> 等待 pong 的标志。 */
    private final Set<String> awaitingPong = ConcurrentHashMap.newKeySet();

    /** 全局出站消息序号(单调递增)。 */
    private final java.util.concurrent.atomic.AtomicLong globalSequence = new java.util.concurrent.atomic.AtomicLong(0);
    /** learnerId -> 最近事件队列(用于重连重放)。 */
    private final Map<String, List<Map<String, Object>>> retainedEvents = new ConcurrentHashMap<>();
    /** learnerId -> 事件序号映射(与 retainedEvents 同步)。 */
    private final Map<String, List<Long>> retainedSequences = new ConcurrentHashMap<>();

    public EduWebSocketHandler(ApplicationEventPublisher publisher,
                               EventHistoryService historyService,
                               com.edu.agent.service.LearnerModelService learnerModelService) {
        this.publisher = publisher;
        this.historyService = historyService;
        this.learnerModelService = learnerModelService;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws Exception {
        String learnerId = extractLearnerId(session);
        if (learnerId == null) {
            session.close(new CloseStatus(CODE_DUPLICATE_CONNECTION, "Missing learner ID"));
            return;
        }

        // 单用户单连接: 踢掉旧连接(4002)
        WebSocketSession old = sessions.put(learnerId, session);
        if (old != null && old.isOpen()) {
            try {
                sendJson(old, Map.of(
                        "type", "error",
                        "code", "duplicate_connection",
                        "message", "Another connection took over"));
                old.close(new CloseStatus(CODE_DUPLICATE_CONNECTION, "duplicate_connection"));
            } catch (Exception e) {
                log.warn("[WebSocket] failed to kick old connection: learner={}", learnerId);
            }
        }

        String sessionId = session.getId();
        lastActivity.put(sessionId, System.currentTimeMillis());

        // 启动心跳检测
        scheduleHeartbeatCheck(session);

        log.info("[WebSocket] connected: learner={} session={}", learnerId, sessionId);
    }

    /**
     * 重连事件重放: 客户端带 last_seq 时,重发 (last_seq, 当前] 区间事件。
     *
     * @return 重放的事件数量,0 表示无需重放。
     */
    public int replayEvents(String learnerId, long lastSeq) {
        List<Map<String, Object>> events = retainedEvents.get(learnerId);
        List<Long> seqs = retainedSequences.get(learnerId);
        if (events == null || seqs == null || events.isEmpty()) {
            return 0;
        }

        WebSocketSession session = sessions.get(learnerId);
        if (session == null || !session.isOpen()) {
            return 0;
        }

        // 找到 lastSeq 之后的事件
        int count = 0;
        for (int i = 0; i < seqs.size(); i++) {
            if (seqs.get(i) > lastSeq) {
                Map<String, Object> event = new LinkedHashMap<>(events.get(i));
                event.put("replayed", true);
                sendJson(session, event);
                count++;
            }
        }

        if (count > 0) {
            log.info("[WebSocket] replayed {} events for learner={} (after seq={})", count, learnerId, lastSeq);
        }
        return count;
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        String learnerId = extractLearnerId(session);
        if (learnerId != null) {
            sessions.remove(learnerId, session);
            // 非主动断开时保留事件用于重连重放(服务端主动关闭时清理)
            if (status.getCode() != CODE_SERVER_SHUTDOWN) {
                log.debug("[WebSocket] retained {} events for learner={} (reconnect pending)",
                        retainedEvents.getOrDefault(learnerId, List.of()).size(), learnerId);
            } else {
                clearRetainedEvents(learnerId);
            }
        }
        lastActivity.remove(session.getId());
        awaitingPong.remove(session.getId());
        log.info("[WebSocket] disconnected: learner={} status={}", learnerId, status);
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) {
        String sessionId = session.getId();
        lastActivity.put(sessionId, System.currentTimeMillis());

        try {
            String learnerId = extractLearnerId(session);
            if (learnerId == null) {
                sendError(session, "missing_learner_id", "Missing learner ID");
                return;
            }

            Map<String, Object> payload = objectMapper.readValue(
                    message.getPayload(), new TypeReference<>() {});
            String action = (String) payload.getOrDefault("action", "");

            // 心跳响应
            if ("pong".equals(action)) {
                awaitingPong.remove(sessionId);
                sendJson(session, Map.of("type", "ack", "action", "pong"));
                return;
            }

            // 消息确认(客户端告知已收到 seq=N)
            if ("ack".equals(action)) {
                Object seq = payload.get("seq");
                if (seq instanceof Number n) {
                    log.debug("[WebSocket] ack: learner={} seq={}", learnerId, n.longValue());
                }
                return;
            }

            // 重连事件重放请求
            if ("reconnect".equals(action)) {
                Object lastSeq = payload.get("last_seq");
                if (lastSeq instanceof Number n) {
                    int replayed = replayEvents(learnerId, n.longValue());
                    sendJson(session, Map.of("type", "reconnect_ack", "replayed", replayed));
                }
                return;
            }

            switch (action) {
                case "submit" -> {
                    Map<String, Object> data = new HashMap<>();
                    data.put("knowledge_id", payload.getOrDefault("knowledge_id", ""));
                    data.put("is_correct", payload.getOrDefault("is_correct", false));
                    data.put("time_spent_seconds", payload.getOrDefault("time_spent_seconds", 0));
                    boolean correct = Boolean.TRUE.equals(payload.get("is_correct"))
                            || Boolean.TRUE.equals(Boolean.valueOf(String.valueOf(payload.getOrDefault("is_correct", false))));
                    double spent = 0;
                    Object ts = payload.get("time_spent_seconds");
                    if (ts instanceof Number n) spent = n.doubleValue();
                    learnerModelService.recordSubmission(
                            learnerId,
                            String.valueOf(payload.getOrDefault("knowledge_id", "")),
                            correct,
                            spent);
                    publisher.publishEvent(new AgentEvent(this, EventType.STUDENT_SUBMISSION,
                            "websocket", learnerId, data));
                    learnerModelService.save(learnerId);
                }
                case "question" -> {
                    Map<String, Object> data = new HashMap<>();
                    data.put("knowledge_id", payload.getOrDefault("knowledge_id", "general"));
                    data.put("question", payload.getOrDefault("question", ""));
                    data.put("debate_mode", payload.getOrDefault("debate_mode", false));
                    data.put("level", payload.getOrDefault("level", "beginner"));
                    data.put("mastery", payload.getOrDefault("mastery", 0.0));
                    publisher.publishEvent(new AgentEvent(this, EventType.STUDENT_QUESTION,
                            "websocket", learnerId, data));
                }
                case "message" -> {
                    Map<String, Object> data = new HashMap<>();
                    data.put("knowledge_id", payload.getOrDefault("knowledge_id", "general"));
                    data.put("question", payload.getOrDefault("message", ""));
                    publisher.publishEvent(new AgentEvent(this, EventType.STUDENT_MESSAGE,
                            "websocket", learnerId, data));
                }
                default -> {
                    sendError(session, "unknown_action", "Unknown action: " + action);
                    return;
                }
            }

            // 发送最近 10 条事件回客户端
            List<AgentEvent> recentEvents = historyService.getHistory(learnerId, null, 10);
            for (AgentEvent event : recentEvents) {
                Map<String, Object> eventData = new LinkedHashMap<>();
                eventData.put("type", "event");
                eventData.put("event_type", event.getType().getWireName());
                eventData.put("source", event.getSourceName());
                eventData.put("data", event.getData());
                eventData.put("timestamp", String.valueOf(event.getTimestamp()));
                sendJson(session, eventData);
            }

        } catch (Exception e) {
            log.error("[WebSocket] error handling message", e);
            sendError(session, "server_error", e.getMessage());
        }
    }

    /**
     * 心跳检测: 每 60s 检查一次,超时发 ping,再等 10s 无 pong 则断开。
     */
    private void scheduleHeartbeatCheck(WebSocketSession session) {
        scheduler.schedule(() -> {
            try {
                String sessionId = session.getId();
                if (!session.isOpen()) return;

                long idle = System.currentTimeMillis() - lastActivity.getOrDefault(sessionId, 0L);
                if (idle < RECEIVE_TIMEOUT_SECONDS * 1000L) {
                    // 未超时,重新调度
                    scheduleHeartbeatCheck(session);
                    return;
                }

                // 发 ping
                sendJson(session, Map.of("type", "ping"));
                awaitingPong.add(sessionId);

                // 等 10s 检查 pong
                scheduler.schedule(() -> {
                    if (awaitingPong.contains(sessionId) && session.isOpen()) {
                        log.info("[WebSocket] heartbeat timeout: session={}", sessionId);
                        try {
                            session.close(new CloseStatus(CODE_HEARTBEAT_TIMEOUT, "heartbeat_timeout"));
                        } catch (IOException e) {
                            log.warn("[WebSocket] failed to close on heartbeat timeout", e);
                        }
                    }
                }, PONG_TIMEOUT_SECONDS, TimeUnit.SECONDS);

                // 继续下一轮检测
                scheduleHeartbeatCheck(session);
            } catch (Exception e) {
                log.warn("[WebSocket] heartbeat check error", e);
            }
        }, RECEIVE_TIMEOUT_SECONDS, TimeUnit.SECONDS);
    }

    /**
     * 服务端关闭时,向所有连接发关闭帧(优雅关闭)。
     */
    public void disconnectAll() {
        List<Map.Entry<String, WebSocketSession>> entries = new ArrayList<>(sessions.entrySet());
        sessions.clear();
        for (Map.Entry<String, WebSocketSession> e : entries) {
            try {
                if (e.getValue().isOpen()) {
                    sendJson(e.getValue(), Map.of(
                            "type", "error",
                            "code", "server_shutdown",
                            "message", "Server is shutting down"));
                    e.getValue().close(new CloseStatus(CODE_SERVER_SHUTDOWN, "server_shutdown"));
                }
            } catch (Exception ex) {
                log.warn("[WebSocket] failed to close on shutdown: {}", e.getKey());
            }
        }
        log.info("[WebSocket] disconnect_all: count={}", entries.size());
    }

    /**
     * 向指定 learner 发消息(供外部调用)。自动附加 sequence 并缓存用于重连重放。
     */
    public boolean sendToLearner(String learnerId, Map<String, Object> data) {
        // 附加序号
        long seq = globalSequence.incrementAndGet();
        Map<String, Object> eventWithSeq = new LinkedHashMap<>(data);
        eventWithSeq.put("seq", seq);

        // 缓存事件用于重连重放
        retainEvent(learnerId, seq, eventWithSeq);

        WebSocketSession ws = sessions.get(learnerId);
        if (ws == null || !ws.isOpen()) {
            // 不在线时事件已在缓存中,重连后自动重放
            return false;
        }
        try {
            sendJson(ws, eventWithSeq);
            return true;
        } catch (Exception e) {
            log.warn("[WebSocket] send failed: learner={}", learnerId);
            sessions.remove(learnerId, ws);
            return false;
        }
    }

    /**
     * 缓存事件用于重连重放(每个 learner 保留最近 RETAINED_EVENTS_PER_LEARNER 条)。
     */
    private void retainEvent(String learnerId, long seq, Map<String, Object> event) {
        List<Map<String, Object>> events = retainedEvents.computeIfAbsent(learnerId, k -> new ArrayList<>());
        List<Long> seqs = retainedSequences.computeIfAbsent(learnerId, k -> new ArrayList<>());

        synchronized (events) {
            events.add(event);
            seqs.add(seq);
            // 超出容量时移除最旧的事件
            while (events.size() > RETAINED_EVENTS_PER_LEARNER) {
                events.removeFirst();
                seqs.removeFirst();
            }
        }
    }

    /**
     * 清理指定 learner 的缓存事件(用户登出或断开时调用)。
     */
    public void clearRetainedEvents(String learnerId) {
        retainedEvents.remove(learnerId);
        retainedSequences.remove(learnerId);
    }

    public int getActiveConnections() {
        return sessions.size();
    }

    private String extractLearnerId(WebSocketSession session) {
        // 优先从 URI template 变量取
        Object uriTemplate = session.getAttributes().get("org.springframework.web.socket.HandlerAttributes.uriTemplate");
        if (uriTemplate instanceof Map<?, ?> vars) {
            Object v = vars.get("learnerId");
            if (v != null) return v.toString();
        }
        // fallback: extract from URI path
        String path = session.getUri() != null ? session.getUri().getPath() : "";
        String[] segments = path.split("/");
        return segments.length > 0 ? segments[segments.length - 1] : null;
    }

    private void sendError(WebSocketSession session, String code, String message) {
        sendJson(session, Map.of("type", "error", "code", code, "message", message));
    }

    private void sendJson(WebSocketSession session, Map<String, Object> data) {
        try {
            session.sendMessage(new TextMessage(objectMapper.writeValueAsString(data)));
        } catch (IOException e) {
            log.warn("[WebSocket] send json failed: {}", e.getMessage());
        }
    }
}
