package com.edu.agent.llm;

import java.util.List;

/**
 * LLM 请求 -- 对齐 Python provider.complete() 的 messages + kwargs。
 *
 * @param messages    消息列表(系统提示 + 用户输入 + 可选历史)
 * @param temperature 温度(0=确定性,1=创造性)
 * @param maxTokens   最大生成 token 数
 * @param model       模型名(null 时使用 provider 默认值)
 */
public record LlmRequest(
        List<LlmMessage> messages,
        Double temperature,
        Integer maxTokens,
        String model
) {
    public LlmRequest {
        if (messages == null || messages.isEmpty()) {
            throw new IllegalArgumentException("messages 不能为空");
        }
        if (temperature == null) temperature = 0.7;
        if (maxTokens == null) maxTokens = 1024;
    }

    /** 便捷构造:仅 messages,其余用默认值。 */
    public LlmRequest(List<LlmMessage> messages) {
        this(messages, 0.7, 1024, null);
    }

    /** 便捷构造:单轮 system + user。 */
    public LlmRequest(String systemPrompt, String userPrompt) {
        this(List.of(LlmMessage.system(systemPrompt), LlmMessage.user(userPrompt)));
    }
}
