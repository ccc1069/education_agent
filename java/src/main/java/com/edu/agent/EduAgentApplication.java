package com.edu.agent;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * 多Agent智能教育系统 - Java版入口。
 * <p>
 * 基于 Spring Boot 3 实现，
 * 使用 Spring ApplicationEvent 作为Agent间事件总线。
 */
@SpringBootApplication
@EnableAsync
@EnableScheduling
public class EduAgentApplication {
    public static void main(String[] args) {
        SpringApplication.run(EduAgentApplication.class, args);
    }
}
