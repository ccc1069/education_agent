package com.edu.agent.core;

import org.springframework.context.ApplicationEvent;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Agent事件基类 -- 所有Agent间通信通过此事件。
 * <p>
 * 利用Spring的ApplicationEventPublisher实现发布-订阅模式，
 * 相当于Python版的EventBus。
 * <p>
 * 面试要点：Spring Event机制 vs 自定义EventBus
 * - Spring Event: 同步/异步可选，与IoC容器深度集成
 * - 自定义EventBus: 更灵活，可跨JVM (如用Kafka/RabbitMQ)
 */
public class AgentEvent extends ApplicationEvent {

    private final String id;
    private final EventType type;
    private final String sourceName;
    private final String learnerId;
    private final Map<String, Object> data;
    private final String correlationId;

    public AgentEvent(Object source, EventType type, String sourceName,
                      String learnerId, Map<String, Object> data) {
        this(source, type, sourceName, learnerId, data, null);
    }

    public AgentEvent(Object source, EventType type, String sourceName,
                      String learnerId, Map<String, Object> data, String correlationId) {
        super(source);
        this.id = UUID.randomUUID().toString();
        this.type = type;
        this.sourceName = sourceName;
        this.learnerId = learnerId;
        this.data = data != null ? data : new HashMap<>();
        this.correlationId = correlationId != null ? correlationId : UUID.randomUUID().toString();
    }

    public String getId() { return id; }
    public EventType getType() { return type; }
    public String getSourceName() { return sourceName; }
    public String getLearnerId() { return learnerId; }
    public Map<String, Object> getData() { return data; }
    public String getCorrelationId() { return correlationId; }
}
