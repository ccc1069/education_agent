package com.edu.agent.llm;

/**
 * LLM 不可用异常 -- 对齐 Python llm.provider.LLMUnavailableError。
 *
 * <p>调用方应捕获此异常并降级到启发式模板。
 */
public class LlmUnavailableException extends RuntimeException {

    public LlmUnavailableException(String message) {
        super(message);
    }

    public LlmUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
