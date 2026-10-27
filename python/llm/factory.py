"""LLM Provider 工厂: 按配置选择。"""

import logging
import os

from config.settings import settings
from llm.minimax_provider import MiniMaxProvider
from llm.mock_provider import MockLLMProvider
from llm.openai_provider import OpenAIProvider
from llm.provider import LLMProvider

logger = logging.getLogger(__name__)


_provider_cache: LLMProvider | None = None
_vision_provider_cache: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    """根据配置和环境变量返回合适的 LLM Provider。

    优先级:
    1. 强制 MOCK: LLM_PROVIDER=mock 或 ENV=test
    2. OpenAI: 有 OPENAI_API_KEY
    3. MiniMax: 有 MINIMAX_API_KEY
    4. 默认 Mock(开发环境无 key 时)
    """
    global _provider_cache
    if _provider_cache is not None:
        return _provider_cache

    provider_name = os.environ.get("LLM_PROVIDER", "").lower()
    env = settings.env.lower()

    if provider_name == "mock" or env in ("test", "ci"):
        _provider_cache = MockLLMProvider()
        logger.info("LLM provider: Mock (env=%s)", env)
        return _provider_cache

    if settings.openai_api_key:
        _provider_cache = OpenAIProvider()
        logger.info("LLM provider: OpenAI (model=%s)", settings.openai_model)
        return _provider_cache

    if settings.minimax_api_key:
        _provider_cache = MiniMaxProvider()
        logger.info("LLM provider: MiniMax (model=%s)", settings.minimax_model)
        return _provider_cache

    logger.warning("No LLM API key configured, falling back to Mock provider")
    _provider_cache = MockLLMProvider()
    return _provider_cache


def resolve_vision_model() -> str:
    """解析拍题用视觉模型名。"""
    explicit = (settings.openai_vision_model or "").strip()
    if explicit:
        return explicit
    base = (settings.openai_model or "").strip()
    probe = OpenAIProvider(model=base or "gpt-4o", api_key=settings.openai_api_key or "x")
    if probe.supports_vision:
        return probe.model
    if "dashscope" in (settings.openai_base_url or "").lower():
        return "qwen-vl-plus"
    return "gpt-4o"


def get_vision_llm_provider() -> LLMProvider:
    """Vision 专用 Provider。

    - 主模型已支持 vision: 复用主 Provider
    - 否则用 OPENAI_VISION_MODEL(或 DashScope 默认 qwen-vl-plus)另建实例
    - test/mock 环境仍走 Mock
    """
    global _vision_provider_cache
    if _vision_provider_cache is not None:
        return _vision_provider_cache

    base = get_llm_provider()
    if isinstance(base, MockLLMProvider) or base.supports_vision:
        _vision_provider_cache = base
        return _vision_provider_cache

    if settings.openai_api_key:
        vision_model = resolve_vision_model()
        _vision_provider_cache = OpenAIProvider(model=vision_model)
        logger.info(
            "Vision LLM provider: OpenAI (model=%s, text_model=%s)",
            vision_model,
            settings.openai_model,
        )
        return _vision_provider_cache

    _vision_provider_cache = base
    return _vision_provider_cache


def reset_provider_cache() -> None:
    """测试用: 重置缓存。"""
    global _provider_cache, _vision_provider_cache
    _provider_cache = None
    _vision_provider_cache = None
