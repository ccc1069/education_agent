package com.edu.agent.llm;

/**
 * 消息角色 -- 对齐 Python llm.provider.LLMRole。
 */
public enum Role {
    SYSTEM("system"),
    USER("user"),
    ASSISTANT("assistant");

    private final String value;

    Role(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }
}
