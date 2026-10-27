"""MiniMax Provider(国产合规)。"""

import logging
import time
from typing import Any

import httpx

from config.settings import settings
from llm.provider import LLMMessage, LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class MiniMaxProvider(LLMProvider):
    """MiniMax 国内合规 LLM。"""

    BASE_URL = "https://api.minimax.chat/v1"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__(
            name="minimax",
            model=model or settings.minimax_model,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
        self.api_key = api_key or settings.minimax_api_key
        if not self.api_key:
            logger.warning("MiniMaxProvider: API key not set")

    async def _call(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        url = f"{self.BASE_URL}/text/chatcompletion_v2"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 1024),
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        start = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
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
