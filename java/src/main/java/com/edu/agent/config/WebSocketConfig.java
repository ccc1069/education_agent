package com.edu.agent.config;

import com.edu.agent.controller.EduWebSocketHandler;
import com.edu.agent.security.JwtAuthenticatingInterceptor;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    private final EduWebSocketHandler handler;
    private final JwtAuthenticatingInterceptor authInterceptor;

    public WebSocketConfig(EduWebSocketHandler handler, JwtAuthenticatingInterceptor authInterceptor) {
        this.handler = handler;
        this.authInterceptor = authInterceptor;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/ws/{learnerId}")
                .setAllowedOrigins("*")
                .addInterceptors(authInterceptor);
    }
}
