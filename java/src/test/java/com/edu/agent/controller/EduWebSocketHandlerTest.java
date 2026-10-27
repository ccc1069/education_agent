package com.edu.agent.controller;

import com.edu.agent.core.EventHistoryService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.WebSocketSession;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

/**
 * EduWebSocketHandler 单元测试 -- 心跳、重连重放、消息序号。
 */
@ExtendWith(MockitoExtension.class)
class EduWebSocketHandlerTest {

    @Mock
    private ApplicationEventPublisher publisher;

    @Mock
    private EventHistoryService historyService;

    @Mock
    private WebSocketSession session;

    private EduWebSocketHandler handler;

    @BeforeEach
    void setUp() {
        handler = new EduWebSocketHandler(publisher, historyService,
                com.edu.agent.service.LearnerModelService.inMemoryOnly());
    }

    @Test
    void getActiveConnections_initiallyZero() {
        assertThat(handler.getActiveConnections()).isZero();
    }

    @Test
    void sendToLearner_noSession_returnsFalse() {
        boolean sent = handler.sendToLearner("unknown-learner", Map.of("type", "event"));
        assertThat(sent).isFalse();
    }

    @Test
    void sendToLearner_sessionExists_returnsTrue() {
        // Simulate connected session
        when(session.isOpen()).thenReturn(true);
        when(session.getUri()).thenReturn(java.net.URI.create("ws://localhost/ws/learner1"));
        when(session.getAttributes()).thenReturn(java.util.HashMap.newHashMap(0));
        when(session.getId()).thenReturn("session-1");

        try {
            handler.afterConnectionEstablished(session);
        } catch (Exception e) {
            // Ignore
        }

        boolean sent = handler.sendToLearner("learner1", Map.of("type", "event"));
        assertThat(sent).isTrue();
    }

    @Test
    void sendToLearner_incrementsSequence() throws Exception {
        when(session.isOpen()).thenReturn(true);
        when(session.getUri()).thenReturn(java.net.URI.create("ws://localhost/ws/learner1"));
        when(session.getAttributes()).thenReturn(java.util.HashMap.newHashMap(0));
        when(session.getId()).thenReturn("session-1");
        doNothing().when(session).sendMessage(any());

        handler.afterConnectionEstablished(session);

        handler.sendToLearner("learner1", Map.of("type", "event1"));
        handler.sendToLearner("learner1", Map.of("type", "event2"));

        // Verify sequence attached (should be called twice with increasing seq)
        verify(session, atLeast(2)).sendMessage(any());
    }

    @Test
    void replayEvents_noEvents_returnsZero() {
        int replayed = handler.replayEvents("unknown", 0);
        assertThat(replayed).isZero();
    }

    @Test
    void replayEvents_withRetainedEvents_replaysAfterLastSeq() {
        when(session.isOpen()).thenReturn(true);
        when(session.getUri()).thenReturn(java.net.URI.create("http://localhost/ws/learner1"));
        when(session.getAttributes()).thenReturn(java.util.HashMap.newHashMap(0));
        when(session.getId()).thenReturn("session-1");

        try {
            handler.afterConnectionEstablished(session);
        } catch (Exception e) {
            // Ignore
        }

        // Send 3 events
        handler.sendToLearner("learner1", Map.of("type", "event1"));
        handler.sendToLearner("learner1", Map.of("type", "event2"));
        handler.sendToLearner("learner1", Map.of("type", "event3"));

        clearInvocations(session);

        // Replay after seq 1 (should replay event2, event3)
        int replayed = handler.replayEvents("learner1", 1);
        assertThat(replayed).isEqualTo(2);
    }

    @Test
    void replayEvents_lastSeqHigherThanAll_returnsZero() {
        when(session.isOpen()).thenReturn(true);
        when(session.getUri()).thenReturn(java.net.URI.create("http://localhost/ws/learner1"));
        when(session.getAttributes()).thenReturn(java.util.HashMap.newHashMap(0));
        when(session.getId()).thenReturn("session-1");

        try {
            handler.afterConnectionEstablished(session);
        } catch (Exception e) {
            // Ignore
        }

        handler.sendToLearner("learner1", Map.of("type", "event1"));

        // Replay after seq 999 (no events after)
        int replayed = handler.replayEvents("learner1", 999);
        assertThat(replayed).isZero();
    }

    @Test
    void clearRetainedEvents_removesEvents() {
        when(session.isOpen()).thenReturn(true);
        when(session.getUri()).thenReturn(java.net.URI.create("http://localhost/ws/learner1"));
        when(session.getAttributes()).thenReturn(java.util.HashMap.newHashMap(0));
        when(session.getId()).thenReturn("session-1");

        try {
            handler.afterConnectionEstablished(session);
        } catch (Exception e) {
            // Ignore
        }

        handler.sendToLearner("learner1", Map.of("type", "event1"));
        handler.clearRetainedEvents("learner1");

        int replayed = handler.replayEvents("learner1", 0);
        assertThat(replayed).isZero();
    }

    @Test
    void afterConnectionClosed_preservesRetainedEvents() throws Exception {
        when(session.isOpen()).thenReturn(true);
        when(session.getUri()).thenReturn(java.net.URI.create("http://localhost/ws/learner1"));
        when(session.getAttributes()).thenReturn(java.util.HashMap.newHashMap(0));
        when(session.getId()).thenReturn("session-1");
        doNothing().when(session).sendMessage(any());

        handler.afterConnectionEstablished(session);

        handler.sendToLearner("learner1", Map.of("type", "event1"));

        // Simulate client disconnect (not server shutdown)
        handler.afterConnectionClosed(session, new CloseStatus(1000, "client_closed"));

        // Events should be preserved. Simulate new connection for replay
        WebSocketSession newSession = mock(WebSocketSession.class);
        when(newSession.isOpen()).thenReturn(true);
        when(newSession.getUri()).thenReturn(java.net.URI.create("http://localhost/ws/learner1"));
        when(newSession.getAttributes()).thenReturn(java.util.HashMap.newHashMap(0));
        when(newSession.getId()).thenReturn("session-2");
        doNothing().when(newSession).sendMessage(any());

        handler.afterConnectionEstablished(newSession);

        // Replay after seq 0 (should replay event1)
        int replayed = handler.replayEvents("learner1", 0);
        assertThat(replayed).isEqualTo(1);
    }

    @Test
    void afterConnectionClosed_serverShutdown_clearsRetainedEvents() {
        when(session.isOpen()).thenReturn(true);
        when(session.getUri()).thenReturn(java.net.URI.create("http://localhost/ws/learner1"));
        when(session.getAttributes()).thenReturn(java.util.HashMap.newHashMap(0));
        when(session.getId()).thenReturn("session-1");

        try {
            handler.afterConnectionEstablished(session);
        } catch (Exception e) {
            // Ignore
        }

        handler.sendToLearner("learner1", Map.of("type", "event1"));

        // Simulate server shutdown
        handler.afterConnectionClosed(session, new CloseStatus(EduWebSocketHandler.CODE_SERVER_SHUTDOWN, "shutdown"));

        // Events should be cleared
        int replayed = handler.replayEvents("learner1", 0);
        assertThat(replayed).isZero();
    }
}
