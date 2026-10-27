package com.edu.agent.observability;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * HealthController 集成测试: 验证健康检查端点。
 */
@SpringBootTest
@ActiveProfiles("test")
class HealthControllerTest {

    @Autowired
    HealthController controller;

    @Test
    void liveness_returnsUp() {
        Map<String, Object> result = controller.liveness();
        assertThat(result).containsEntry("status", "up");
        assertThat(result).containsEntry("alive", true);
    }

    @Test
    void readiness_returnsStatus() {
        Map<String, Object> result = controller.readiness();
        assertThat(result).containsKey("status");
        assertThat(result).containsKey("components");
    }

    @Test
    void readiness_databaseComponentPresent() {
        Map<String, Object> result = controller.readiness();
        @SuppressWarnings("unchecked")
        Map<String, Object> components = (Map<String, Object>) result.get("components");
        assertThat(components).containsKey("database");
    }

    @Test
    void health_returnsFullStatus() {
        Map<String, Object> result = controller.health();
        assertThat(result).containsKey("status");
        assertThat(result).containsKey("alive");
        assertThat(result).containsKey("components");
    }

    @Test
    void health_jvmComponentPresent() {
        Map<String, Object> result = controller.health();
        @SuppressWarnings("unchecked")
        Map<String, Object> components = (Map<String, Object>) result.get("components");
        assertThat(components).containsKey("jvm");
        assertThat(components).containsKey("database");
    }
}
