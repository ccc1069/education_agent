package com.edu.agent.llm;

/**
 * 单条消息 -- 对齐 Python llm.provider.LLMMessage。
 *
 * @param role    消息角色(system / user / assistant)
 * @param content 文本内容
 */
public record LlmMessage(Role role, String content) {
    public LlmMessage {
        if (role == null) throw new IllegalArgumentException("role 不能为空");
        if (content == null) content = "";
    }

    public static LlmMessage system(String content) {
        return new LlmMessage(Role.SYSTEM, content);
    }

    public static LlmMessage user(String content) {
        return new LlmMessage(Role.USER, content);
    }

    public static LlmMessage assistant(String content) {
        return new LlmMessage(Role.ASSISTANT, content);
    }
}
