package com.edu.agent.observability;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * MetricsFilter 单元测试: 验证路径归一化逻辑。
 */
class MetricsFilterTest {

    @Test
    void normalizePath_numericId_replacedWithPlaceholder() {
        assertThat(MetricsFilter.normalizePath("/api/learners/123/submissions"))
                .isEqualTo("/api/learners/:id/submissions");
    }

    @Test
    void normalizePath_uuid_replacedWithPlaceholder() {
        assertThat(MetricsFilter.normalizePath("/api/learners/550e8400-e29b-41d4-a716-446655440000"))
                .isEqualTo("/api/learners/:id");
    }

    @Test
    void normalizePath_staticPath_unchanged() {
        assertThat(MetricsFilter.normalizePath("/api/learners/me"))
                .isEqualTo("/api/learners/me");
    }

    @Test
    void normalizePath_multipleIds_allReplaced() {
        assertThat(MetricsFilter.normalizePath("/api/learners/42/questions/99"))
                .isEqualTo("/api/learners/:id/questions/:id");
    }

    @Test
    void normalizePath_emptyPath_returnsRoot() {
        assertThat(MetricsFilter.normalizePath("")).isEqualTo("/");
    }

    @Test
    void normalizePath_rootPath_unchanged() {
        assertThat(MetricsFilter.normalizePath("/")).isEqualTo("/");
    }
}
