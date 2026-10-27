"""OpenAI Provider(支持任意 OpenAI 兼容 API)。"""

import logging
import time
from typing import Any

import httpx

from config.settings import settings
from llm.provider import LLMMessage, LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI / 兼容 API(如 Azure OpenAI、Together AI、本地 vLLM)。

    通过 base_url 切换:
        https://api.openai.com/v1  -> OpenAI 官方
        https://api.minimax.io/v1   -> MiniMax
        http://localhost:11434/v1  -> 本地 Ollama
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        super().__init__(
            name="openai",
            model=model or settings.openai_model,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
        self.api_key = api_key or settings.openai_api_key
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        if not self.api_key:
            logger.warning("OpenAIProvider: API key not set, calls will fail")

    @property
    def supports_vision(self) -> bool:
        """多模态模型名启发式匹配(OpenAI / DashScope / 通义 VL 等)。"""
        m = self.model.lower()
        return any(
            k in m
            for k in (
                "gpt-4o",
                "gpt-4-vision",
                "gpt-4-turbo",
                "-vision",
                "o1",
                "o3",
                "qwen-vl",
                "qwen2-vl",
                "qwen2.5-vl",
                "qwen3-vl",
                "vl-plus",
                "vl-max",
                "vl-flash",
                "glm-4v",
                "gemini",
            )
        )

    async def _call(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 1024),
            "stream": False,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        start = time.monotonic()
        # httpx 超时略小于外层 wait_for,避免双重取消竞态;不继承系统代理环境变量的话
        # 可由 HTTP(S)_PROXY 控制。读超时单独放宽到 self.timeout。
        timeout = httpx.Timeout(self.timeout, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
        latency_ms = (time.monotonic() - start) * 1000

        data = response.json()
        choice = data["choices"][0]
        usage = data.get("usage", {})

        return LLMResponse(
            content=choice["message"]["content"],
            model=data.get("model", self.model),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            finish_reason=choice.get("finish_reason", "stop"),
            latency_ms=latency_ms,
            metadata={"provider": self.name},
        )
