package com.edu.agent.config;

import com.edu.agent.core.KnowledgeGraph;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * 知识图谱配置 -- 启动时构建样例数学图谱,供 Controller 和 Agent 共享。
 * 后续可改为从 DB 加载。
 */
@Configuration
public class KnowledgeGraphConfig {

    @Bean
    public KnowledgeGraph knowledgeGraph() {
        return KnowledgeGraph.buildSampleMathGraph();
    }
}
