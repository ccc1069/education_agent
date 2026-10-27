package com.edu.agent.llm;

/**
 * LLM Provider 接口 -- 对齐 Python llm.provider.LLMProvider。
 *
 * <p>实现类需处理:
 * <ul>
 *   <li>HTTP 调用 OpenAI 兼容 API</li>
 *   <li>响应解析(JSON -> LlmResponse)</li>
 *   <li>错误处理(网络/超时/HTTP 错误)</li>
 * </ul>
 *
 * <p>重试与熔断由 {@link LlmService} 统一处理,provider 只需单次调用。
 */
public interface LlmProvider {

    /**
     * 执行单次 LLM 调用。
     *
     * @param request 请求
     * @return 响应
     * @throws LlmUnavailableException 调用失败(网络/超时/HTTP 错误)
     */
    LlmResponse chat(LlmRequest request);

    /**
     * 是否可用(API key 已配置)。
     */
    boolean isAvailable();

    /**
     * Provider 名称("openai" / "mock")。
     */
    String name();
}
