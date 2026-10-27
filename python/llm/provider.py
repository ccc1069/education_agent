"""LLM Provider 抽象基类 + 数据模型。"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """LLM 调用基础异常。"""


class LLMUnavailableError(LLMError):
    """所有重试耗尽,LLM 不可用。调用方应降级到模板回复。"""


class LLMRole(str, Enum):
    """OpenAI 兼容的角色枚举。"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class LLMMessage:
    """单条消息(OpenAI chat completions 格式)。

    Args:
        role: system / user / assistant
        content: 文本内容
        images: 可选的图像列表(P2#16c 多模态)。每项为 data URL
            (如 "data:image/png;base64,iVBOR...") 或公开 http(s) URL。
            非 None 且非空时,provider 会以 OpenAI Vision 格式构造
            content=[{type:text,...},{type:image_url,...}]。
    """

    role: LLMRole
    content: str
    images: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """转 OpenAI 兼容 dict。

        无图像: {"role": ..., "content": "text"}
        有图像: {"role": ..., "content": [{type:text}, {type:image_url}, ...]}
        """
        if not self.images:
            return {"role": self.role.value, "content": self.content}
        parts: list[dict[str, Any]] = [{"type": "text", "text": self.content}]
        for img in self.images:
            parts.append({"type": "image_url", "image_url": {"url": img}})
        return {"role": self.role.value, "content": parts}


@dataclass
class LLMResponse:
    """LLM 响应数据。"""

    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str = "stop"
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """LLM Provider 抽象基类。

    子类需实现 `_call()` 方法。基类提供:
    - 重试(指数退避)
    - 熔断器(失败率超阈值时降级)
    - token 计数与成本记录
    - 流式接口(可选,默认 NotImplemented)
    """

    def __init__(
        self,
        name: str,
        model: str,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_backoff_factor: float = 2.0,
        retry_initial_delay: float = 1.0,
    ) -> None:
        self.name = name
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff_factor = retry_backoff_factor
        self.retry_initial_delay = retry_initial_delay

        # 熔断器状态
        self._consecutive_failures = 0
        self._failure_threshold = 5  # 连续 5 次失败后熔断
        self._circuit_open_until: datetime | None = None

    @abstractmethod
    async def _call(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        """实际调用 LLM 的方法,子类实现。"""
        ...

    @property
    def supports_vision(self) -> bool:
        """是否支持图像输入(P2#16c)。子类可覆盖。"""
        return False

    def _is_circuit_open(self) -> bool:
        if self._circuit_open_until is None:
            return False
        if datetime.now(timezone.utc) >= self._circuit_open_until:
            # 半开: 重置熔断,允许一次试探
            self._circuit_open_until = None
            self._consecutive_failures = 0
            return False
        return True

    def _record_success(self) -> None:
        if self._consecutive_failures > 0:
            logger.info("[%s] circuit recovering after success", self.name)
        self._consecutive_failures = 0
        self._circuit_open_until = None

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._failure_threshold:
            # 熔断 60 秒
            from datetime import timedelta

            self._circuit_open_until = datetime.now(timezone.utc) + timedelta(seconds=60)
            logger.warning(
                "[%s] circuit OPENED after %d failures (recovery in 60s)",
                self.name,
                self._consecutive_failures,
            )

    async def complete(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        """主入口: 调用 LLM,带重试和熔断。

        自动记录:
        - LLM_REQUEST_DURATION (status: success/error)
        - LLM_TOKENS_USED (prompt/completion)

        Raises:
            LLMUnavailableError: 所有重试失败或熔断器开启。
        """
        if self._is_circuit_open():
            raise LLMUnavailableError(
                f"Circuit breaker open for {self.name}, retry in 60s"
            )

        import asyncio
        import time

        delay = self.retry_initial_delay
        last_error: Exception | None = None
        start_time = time.perf_counter()
        call_status = "error"

        try:
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = await asyncio.wait_for(
                        self._call(messages, **kwargs), timeout=self.timeout
                    )
                    self._record_success()
                    call_status = "success"
                    logger.debug(
                        "[%s] call success attempt=%d tokens=%d latency=%dms",
                        self.name,
                        attempt,
                        response.total_tokens,
                        int(response.latency_ms),
                    )
                    # 记录 token 使用量
                    _record_llm_tokens(self.name, response.model, response)
                    return response
                except asyncio.TimeoutError:
                    last_error = LLMError(f"{self.name} timeout after {self.timeout}s")
                    logger.warning("[%s] timeout attempt=%d", self.name, attempt)
                    # 超时不再重试: 再等 30s×N 只会拖死 HTTP 客户端,直接降级模板
                    break
                except Exception as e:
                    last_error = e
                    logger.warning("[%s] error attempt=%d: %s", self.name, attempt, str(e))

                if attempt < self.max_retries:
                    await asyncio.sleep(delay)
                    delay *= self.retry_backoff_factor

            self._record_failure()
            raise LLMUnavailableError(
                f"{self.name} failed after {self.max_retries} attempts: {last_error}"
            )
        finally:
            duration = time.perf_counter() - start_time
            _record_llm_duration(self.name, self.model, call_status, duration)


def _record_llm_tokens(provider: str, model: str, response: LLMResponse) -> None:
    """记录 LLM token 消耗到 Prometheus(若可观测性可用)。"""
    try:
        from observability.metrics import LLM_TOKENS_USED

        if response.prompt_tokens > 0:
            LLM_TOKENS_USED.labels(provider=provider, model=model, kind="prompt").inc(
                response.prompt_tokens
            )
        if response.completion_tokens > 0:
            LLM_TOKENS_USED.labels(
                provider=provider, model=model, kind="completion"
            ).inc(response.completion_tokens)
    except ImportError:
        pass


def _record_llm_duration(
    provider: str, model: str, status: str, duration: float
) -> None:
    """记录 LLM 调用耗时到 Prometheus(若可观测性可用)。"""
    try:
        from observability.metrics import LLM_REQUEST_DURATION

        LLM_REQUEST_DURATION.labels(
            provider=provider, model=model, status=status
        ).observe(duration)
    except ImportError:
        pass

    async def complete_text(self, prompt: str, system: str = "") -> str:
        """便捷方法: 单轮 prompt -> 文本。"""
        messages: list[LLMMessage] = []
        if system:
            messages.append(LLMMessage(role=LLMRole.SYSTEM, content=system))
        messages.append(LLMMessage(role=LLMRole.USER, content=prompt))
        response = await self.complete(messages)
        return response.content
