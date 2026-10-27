"""LLM 工厂 + 各 Provider 单元测试(用 httpx mock / monkeypatch 避免真实调用)。"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from llm.factory import get_llm_provider, reset_provider_cache
from llm.minimax_provider import MiniMaxProvider
from llm.mock_provider import MockLLMProvider
from llm.openai_provider import OpenAIProvider
from llm.provider import LLMMessage, LLMProvider, LLMResponse, LLMRole


# ---------- factory ----------


def test_factory_returns_mock_in_test_env():
    reset_provider_cache()
    provider = get_llm_provider()
    assert isinstance(provider, MockLLMProvider)


def test_factory_returns_mock_when_explicit(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    reset_provider_cache()
    provider = get_llm_provider()
    assert isinstance(provider, MockLLMProvider)


def test_factory_caches_provider():
    reset_provider_cache()
    p1 = get_llm_provider()
    p2 = get_llm_provider()
    assert p1 is p2


def test_factory_reset_clears_cache():
    reset_provider_cache()
    p1 = get_llm_provider()
    reset_provider_cache()
    p2 = get_llm_provider()
    assert p1 is not p2


def test_factory_returns_openai_when_api_key_set(monkeypatch):
    """设置 OPENAI_API_KEY 且非 test 环境时应返回 OpenAIProvider。"""
    from config.settings import settings

    reset_provider_cache()
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-key")
    monkeypatch.setattr(settings, "env", "dev")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    provider = get_llm_provider()
    from llm.openai_provider import OpenAIProvider

    assert isinstance(provider, OpenAIProvider)
    reset_provider_cache()


def test_factory_returns_minimax_when_only_minimax_key_set(monkeypatch):
    """设置 MINIMAX_API_KEY(无 OpenAI key)且非 test 环境时应返回 MiniMaxProvider。"""
    from config.settings import settings

    reset_provider_cache()
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "minimax_api_key", "mm-test-key")
    monkeypatch.setattr(settings, "env", "dev")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    provider = get_llm_provider()
    assert isinstance(provider, MiniMaxProvider)
    reset_provider_cache()


def test_factory_falls_back_to_mock_without_keys(monkeypatch):
    """无任何 API key 且非 test 环境时应回退到 Mock。"""
    from config.settings import settings

    reset_provider_cache()
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "minimax_api_key", "")
    monkeypatch.setattr(settings, "env", "dev")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    provider = get_llm_provider()
    assert isinstance(provider, MockLLMProvider)
    reset_provider_cache()


# ---------- MiniMaxProvider (mocked httpx) ----------


@pytest.mark.asyncio
async def test_minimax_provider_call_returns_response():
    """用 httpx Mock 测试 MiniMaxProvider 调用流程。"""
    provider = MiniMaxProvider(api_key="test-key", model="test-model")

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "model": "test-model",
        "choices": [
            {"message": {"content": "hello"}, "finish_reason": "stop"}
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        response = await provider._call(
            [LLMMessage(role=LLMRole.USER, content="hi")]
        )

    assert response.content == "hello"
    assert response.prompt_tokens == 10
    assert response.completion_tokens == 5
    assert response.total_tokens == 15
    assert response.finish_reason == "stop"


@pytest.mark.asyncio
async def test_minimax_provider_raises_on_http_error():
    """HTTP 错误应抛 raise_for_status。"""
    provider = MiniMaxProvider(api_key="test-key")

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server error", request=MagicMock(), response=MagicMock()
    )

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            await provider._call([LLMMessage(role=LLMRole.USER, content="hi")])


def test_minimax_provider_warns_without_api_key():
    """无 API key 应只 warning,不抛异常。"""
    provider = MiniMaxProvider(api_key="")
    assert provider.api_key == ""


# ---------- provider base class (circuit breaker) ----------


@pytest.mark.asyncio
async def test_provider_circuit_breaker_opens_after_failures():
    """连续失败应触发熔断。"""
    from llm.provider import LLMProvider, LLMUnavailableError

    class _FailProvider(LLMProvider):
        async def _call(self, messages, **kwargs):
            raise RuntimeError("simulated failure")

    provider = _FailProvider(name="fail", model="m", max_retries=1)
    provider._failure_threshold = 2  # 触发阈值

    # 前两次 complete() 内部各 retry 2 次,每次都失败 -> _record_failure() 被调用 2 次
    for _ in range(2):
        with pytest.raises(LLMUnavailableError, match="failed after"):
            await provider.complete([LLMMessage(role=LLMRole.USER, content="x")])

    # 第三次应被熔断
    with pytest.raises(LLMUnavailableError, match="Circuit breaker open"):
        await provider.complete([LLMMessage(role=LLMRole.USER, content="x")])


# ---------- OpenAIProvider (mocked httpx) ----------


@pytest.mark.asyncio
async def test_openai_provider_call_returns_response():
    """用 httpx Mock 测试 OpenAIProvider 调用流程。"""
    provider = OpenAIProvider(api_key="test-key", model="gpt-4", base_url="https://api.openai.com/v1")

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "model": "gpt-4",
        "choices": [
            {"message": {"content": "Hello!"}, "finish_reason": "stop"}
        ],
        "usage": {
            "prompt_tokens": 8,
            "completion_tokens": 4,
            "total_tokens": 12,
        },
    }

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        response = await provider._call(
            [LLMMessage(role=LLMRole.USER, content="hi")]
        )

    assert response.content == "Hello!"
    assert response.prompt_tokens == 8
    assert response.completion_tokens == 4
    assert response.total_tokens == 12
    assert response.model == "gpt-4"


@pytest.mark.asyncio
async def test_openai_provider_raises_on_http_error():
    """HTTP 错误应抛 raise_for_status。"""
    provider = OpenAIProvider(api_key="test-key")

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server error", request=MagicMock(), response=MagicMock()
    )

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            await provider._call([LLMMessage(role=LLMRole.USER, content="hi")])


def test_openai_provider_warns_without_api_key():
    """无 API key 应只 warning,不抛异常。"""
    provider = OpenAIProvider(api_key="")
    assert provider.api_key == ""


def test_openai_provider_strips_trailing_slash_from_base_url():
    """base_url 末尾的 / 应被去除。"""
    provider = OpenAIProvider(api_key="k", base_url="https://api.openai.com/v1/")
    assert provider.base_url == "https://api.openai.com/v1"
