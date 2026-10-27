package com.edu.agent.security;

import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.http.server.ServletServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.server.HandshakeInterceptor;

import java.util.Map;

/**
 * WebSocket JWT 握手鉴权 -- 对齐 Python api/websocket.py _authenticate_ws。
 *
 * <p>客户端在 query string 中传 token:
 * <pre>ws://host/ws/{learnerId}?token=JWT_ACCESS_TOKEN</pre>
 *
 * <p>握手阶段校验 token,失败时返回 401 UNAUTHORIZED 拒绝连接。
 * 成功时将 userId / role 存入 session attributes,供 handler 使用。
 */
@Slf4j
@Component
public class JwtAuthenticatingInterceptor implements HandshakeInterceptor {

    private static final String TOKEN_PARAM = "token";
    public static final String ATTR_USER_ID = "ws.userId";
    public static final String ATTR_ROLE = "ws.role";
    public static final String ATTR_EMAIL = "ws.email";

    private final JwtUtil jwtUtil;

    public JwtAuthenticatingInterceptor(JwtUtil jwtUtil) {
        this.jwtUtil = jwtUtil;
    }

    @Override
    public boolean beforeHandshake(ServerHttpRequest request, ServerHttpResponse response,
                                   WebSocketHandler wsHandler, Map<String, Object> attributes) {
        String token = extractToken(request);
        if (token == null || token.isBlank()) {
            log.warn("[WebSocket] handshake rejected: missing token");
            response.setStatusCode(HttpStatus.UNAUTHORIZED);
            return false;
        }

        JwtUtil.TokenData data = jwtUtil.decodeAccessToken(token);
        if (data == null) {
            log.warn("[WebSocket] handshake rejected: invalid token");
            response.setStatusCode(HttpStatus.UNAUTHORIZED);
            return false;
        }

        attributes.put(ATTR_USER_ID, data.userId());
        attributes.put(ATTR_ROLE, data.role());
        attributes.put(ATTR_EMAIL, data.email());
        log.debug("[WebSocket] handshake accepted: user={} role={}", data.userId(), data.role());
        return true;
    }

    @Override
    public void afterHandshake(ServerHttpRequest request, ServerHttpResponse response,
                               WebSocketHandler wsHandler, Exception exception) {
        // no-op
    }

    private String extractToken(ServerHttpRequest request) {
        if (request instanceof ServletServerHttpRequest servletReq) {
            return servletReq.getServletRequest().getParameter(TOKEN_PARAM);
        }
        // fallback: parse from URI query
        String query = request.getURI().getQuery();
        if (query != null) {
            for (String pair : query.split("&")) {
                String[] kv = pair.split("=", 2);
                if (kv.length == 2 && TOKEN_PARAM.equals(kv[0])) {
                    return kv[1];
                }
            }
        }
        return null;
    }
}
