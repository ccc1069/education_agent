"""Embedding Provider: OpenAI 兼容 API / Mock。

设计:
- OpenAIEmbeddingProvider: 走 /embeddings,模型与维度由独立 EMBEDDING_* 配置
- MockEmbeddingProvider: 基于文本哈希的确定性 384 维向量(测试)
- 工厂按配置选择;DashScope 默认 text-embedding-v3,OpenAI 默认 text-embedding-3-large
"""

import hashlib
import logging
import math
from abc import ABC, abstractmethod
from typing import Any

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

_MODEL_DEFAULT_DIMS: dict[str, int] = {
    "text-embedding-3-large": 3072,
    "text-embedding-3-small": 1536,
    "text-embedding-ada-002": 1536,
    "text-embedding-v4": 1024,
    "text-embedding-v3": 1024,
    "text-embedding-v2": 1536,
    "text-embedding-v1": 1536,
}


def resolve_embedding_base_url() -> str:
    return (settings.embedding_base_url or settings.openai_base_url or "").rstrip("/")


def resolve_embedding_api_key() -> str:
    return settings.embedding_api_key or settings.openai_api_key or ""


def resolve_embedding_model(base_url: str | None = None) -> str:
    """显式 EMBEDDING_MODEL 优先;否则按 base_url 推断。"""
    if settings.embedding_model.strip():
        return settings.embedding_model.strip()
    url = (base_url or resolve_embedding_base_url()).lower()
    if "dashscope" in url:
        return "text-embedding-v3"
    return "text-embedding-3-large"


def resolve_embedding_dimensions(model: str) -> int:
    """维度: 显式 EMBEDDING_DIMENSIONS 在「作用于当前模型」时生效,否则按模型默认。"""
    if settings.embedding_dimensions > 0:
        configured = settings.embedding_model.strip()
        if not configured or configured == model:
            return settings.embedding_dimensions
    return _MODEL_DEFAULT_DIMS.get(model, 1024)


class EmbeddingProvider(ABC):
    """Embedding 抽象基类。"""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def dimension(self) -> int: ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """单文本 -> 向量。"""
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量 embed(性能更好)。"""
        ...


class MockEmbeddingProvider(EmbeddingProvider):
    """Mock Embedding: 基于文本哈希的确定性向量。

    用途:
    - 单元测试(无网络依赖)
    - 开发环境无 API key 时
    - LLM_PROVIDER=mock 自动启用

    特点:
    - 384 维(与 sentence-transformers MiniLM 一致)
    - 确定性: 相同文本 -> 相同向量
    - 语义近似: 相同词的文本向量夹角余弦较高(用 word-level hashing 聚合)
    """

    _DIM = 384

    def __init__(self) -> None:
        self._model_name = "mock-embedding"

    @property
    def name(self) -> str:
        return "mock"

    @property
    def dimension(self) -> int:
        return self._DIM

    async def embed(self, text: str) -> list[float]:
        return self._hash_to_vector(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_to_vector(t) for t in texts]

    def _add_hash(self, vec: list[float], token: str) -> None:
        """将 token 的 MD5 哈希叠加到向量上。"""
        h = hashlib.md5(token.encode("utf-8")).digest()
        for i in range(0, self._DIM, 4):
            chunk = h[i % 16 : i % 16 + 4]
            if len(chunk) < 4:
                chunk = chunk + b"\x00" * (4 - len(chunk))
            value = int.from_bytes(chunk, "big") / 0xFFFFFFFF - 0.5
            vec[i] += value

    def _hash_to_vector(self, text: str) -> list[float]:
        """词级 + 字符级 2-gram 哈希聚合 -> 归一化向量。

        - 英文: 按空格分词,每个词哈希叠加
        - 中文/混合: 取 2 字符 n-gram,共享子串的文本余弦相似度较高
        - 相同文本 -> 相同向量(确定性)
        """
        vec = [0.0] * self._DIM
        text = text.lower().strip()
        if not text:
            return vec

        for word in text.split():
            self._add_hash(vec, word)

        chars = "".join(text.split())
        for i in range(len(chars) - 1):
            self._add_hash(vec, chars[i : i + 2])

        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI 兼容 /embeddings 接口。

    支持 OpenAI 官方与 DashScope compatible-mode 等。
    模型/密钥/地址优先读 EMBEDDING_*,再回退 OPENAI_*。
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        self.base_url = (base_url or resolve_embedding_base_url()).rstrip("/")
        self.api_key = api_key if api_key is not None else resolve_embedding_api_key()
        self._model = model or resolve_embedding_model(self.base_url)
        self._dimension = (
            dimensions
            if dimensions is not None and dimensions > 0
            else resolve_embedding_dimensions(self._model)
        )
        if not self.api_key:
            logger.warning("OpenAIEmbeddingProvider: API key not set, calls will fail")

    @property
    def name(self) -> str:
        return "openai_compatible"

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model(self) -> str:
        return self._model

    async def embed(self, text: str) -> list[float]:
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        url = f"{self.base_url}/embeddings"
        payload: dict[str, Any] = {
            "model": self._model,
            "input": texts,
        }
        # DashScope v3/v4 与 OpenAI text-embedding-3 均可选维度
        if self._dimension > 0 and (
            self._model.startswith("text-embedding-v")
            or self._model.startswith("text-embedding-3")
        ):
            payload["dimensions"] = self._dimension

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

        data = response.json()
        items = sorted(data["data"], key=lambda d: d["index"])
        vectors = [item["embedding"] for item in items]
        if vectors:
            actual_dim = len(vectors[0])
            if actual_dim != self._dimension:
                logger.warning(
                    "Embedding dim: configured=%d actual=%d (model=%s), adopting actual",
                    self._dimension,
                    actual_dim,
                    self._model,
                )
                self._dimension = actual_dim
        return vectors


_embedding_provider_cache: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """工厂: 按配置返回 EmbeddingProvider。

    优先级:
    1. ENV=test 或 LLM_PROVIDER=mock -> MockEmbeddingProvider
    2. 有 EMBEDDING_API_KEY 或 OPENAI_API_KEY -> OpenAIEmbeddingProvider
    3. 兜底 -> MockEmbeddingProvider
    """
    global _embedding_provider_cache
    if _embedding_provider_cache is not None:
        return _embedding_provider_cache

    import os

    provider_name = os.environ.get("LLM_PROVIDER", "").lower()
    env = settings.env.lower()

    if provider_name == "mock" or env in ("test", "ci"):
        _embedding_provider_cache = MockEmbeddingProvider()
        logger.info("Embedding provider: Mock (env=%s)", env)
        return _embedding_provider_cache

    api_key = resolve_embedding_api_key()
    if api_key:
        provider = OpenAIEmbeddingProvider()
        _embedding_provider_cache = provider
        logger.info(
            "Embedding provider: OpenAI-compatible (model=%s dim=%d base=%s)",
            provider.model,
            provider.dimension,
            provider.base_url,
        )
        return _embedding_provider_cache

    logger.warning("No embedding API key, falling back to Mock provider")
    _embedding_provider_cache = MockEmbeddingProvider()
    return _embedding_provider_cache


def reset_embedding_provider_cache() -> None:
    """测试用: 重置缓存。"""
    global _embedding_provider_cache
    _embedding_provider_cache = None
