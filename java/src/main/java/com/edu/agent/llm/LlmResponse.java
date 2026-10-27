package com.edu.agent.llm;

/**
 * LLM 响应 -- 对齐 Python llm.provider.LLMResponse。
 *
 * @param content          生成的文本内容
 * @param model            实际使用的模型名
 * @param promptTokens     输入 token 数
 * @param completionTokens 输出 token 数
 * @param totalTokens      总 token 数
 * @param finishReason     结束原因(stop / length / error)
 * @param latencyMs        调用耗时(毫秒)
 */
public record LlmResponse(
        String content,
        String model,
        int promptTokens,
        int completionTokens,
        int totalTokens,
        String finishReason,
        double latencyMs
) {
    public LlmResponse {
        if (content == null) content = "";
        if (model == null) model = "unknown";
        if (finishReason == null) finishReason = "stop";
    }

    /** 简化构造:仅 content + model,其余为 0。 */
    public LlmResponse(String content, String model) {
        this(content, model, 0, 0, 0, "stop", 0.0);
    }

    /** 从错误构造的降级响应。 */
    public static LlmResponse error(String errorMessage) {
        return new LlmResponse(errorMessage, "error", 0, 0, 0, "error", 0.0);
    }

    public boolean isError() {
        return "error".equals(finishReason);
    }
}
