"""RAG 模块测试: Embedding + Chunking + VectorStore + RAGService。"""

import math
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from rag import (
    EmbeddingProvider,
    InMemoryVectorStore,
    MockEmbeddingProvider,
    OpenAIEmbeddingProvider,
    ScoredChunk,
    cosine_similarity,
    chunk_text,
    count_tokens,
    get_embedding_provider,
    reset_embedding_provider_cache,
)


# ---------- cosine_similarity ----------


def test_cosine_similarity_identical_vectors():
    v = [1.0, 0.0, 0.0]
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert cosine_similarity(a, b) == pytest.approx(0.0)


def test_cosine_similarity_opposite_vectors():
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert cosine_similarity(a, b) == pytest.approx(-1.0)


def test_cosine_similarity_empty_vectors():
    assert cosine_similarity([], []) == 0.0


def test_cosine_similarity_different_lengths():
    assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0


def test_cosine_similarity_zero_vector():
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


# ---------- MockEmbeddingProvider ----------


def test_mock_embedding_provider_returns_deterministic_vector():
    provider = MockEmbeddingProvider()
    v1 = provider._hash_to_vector("hello world")
    v2 = provider._hash_to_vector("hello world")
    assert v1 == v2


def test_mock_embedding_provider_dimension_is_384():
    provider = MockEmbeddingProvider()
    assert provider.dimension == 384
    v = provider._hash_to_vector("test")
    assert len(v) == 384


def test_mock_embedding_provider_unit_norm():
    provider = MockEmbeddingProvider()
    v = provider._hash_to_vector("a test sentence with multiple words")
    norm = math.sqrt(sum(x * x for x in v))
    assert norm == pytest.approx(1.0, abs=1e-6)


def test_mock_embedding_provider_similar_texts_are_deterministic():
    """Mock embedding 不保证语义相似度,但相同文本必须返回相同向量。"""
    provider = MockEmbeddingProvider()
    v1 = provider._hash_to_vector("some text")
    v2 = provider._hash_to_vector("some text")
    assert v1 == v2


@pytest.mark.asyncio
async def test_mock_embedding_provider_embed_and_embed_batch():
    provider = MockEmbeddingProvider()
    v = await provider.embed("hello")
    assert len(v) == 384

    vectors = await provider.embed_batch(["a", "b", "c"])
    assert len(vectors) == 3
    assert all(len(v) == 384 for v in vectors)


@pytest.mark.asyncio
async def test_mock_embedding_provider_empty_batch():
    provider = MockEmbeddingProvider()
    assert await provider.embed_batch([]) == []


# ---------- Embedding factory ----------


def test_embedding_factory_returns_mock_in_test_env():
    reset_embedding_provider_cache()
    provider = get_embedding_provider()
    assert isinstance(provider, MockEmbeddingProvider)


def test_embedding_factory_resets_cache():
    reset_embedding_provider_cache()
    p1 = get_embedding_provider()
    reset_embedding_provider_cache()
    p2 = get_embedding_provider()
    assert p1 is not p2


# ---------- OpenAIEmbeddingProvider (mocked httpx) ----------


@pytest.mark.asyncio
async def test_openai_embedding_provider_embed_returns_vector():
    provider = OpenAIEmbeddingProvider(api_key="test-key", base_url="https://api.openai.com/v1")

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "model": "text-embedding-3-large",
        "data": [
            {"index": 0, "embedding": [0.1, 0.2, 0.3]},
        ],
        "usage": {"prompt_tokens": 5, "total_tokens": 5},
    }

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        vec = await provider.embed("hello")

    assert vec == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_openai_embedding_provider_embed_batch_sorts_by_index():
    provider = OpenAIEmbeddingProvider(api_key="test-key", base_url="https://api.openai.com/v1")

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    # 服务端乱序返回
    mock_response.json.return_value = {
        "data": [
            {"index": 2, "embedding": [0.3]},
            {"index": 0, "embedding": [0.1]},
            {"index": 1, "embedding": [0.2]},
        ]
    }

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        vectors = await provider.embed_batch(["a", "b", "c"])

    assert vectors == [[0.1], [0.2], [0.3]]


@pytest.mark.asyncio
async def test_openai_embedding_provider_embed_batch_empty_input():
    provider = OpenAIEmbeddingProvider(api_key="test-key")
    assert await provider.embed_batch([]) == []


def test_openai_embedding_provider_dimension():
    p = OpenAIEmbeddingProvider(
        api_key="k",
        model="text-embedding-3-large",
        base_url="https://api.openai.com/v1",
    )
    assert p.dimension == 3072


def test_openai_embedding_provider_dashscope_defaults():
    p = OpenAIEmbeddingProvider(
        api_key="k",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    assert p.model == "text-embedding-v3"
    assert p.dimension == 1024


# ---------- chunking ----------


def test_chunk_text_empty_returns_empty_list():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_text_short_text_returns_single_chunk():
    chunks = chunk_text("This is a short sentence.")
    assert len(chunks) == 1
    assert chunks[0].content == "This is a short sentence."
    assert chunks[0].chunk_index == 0


def test_chunk_text_multiple_sentences_aggregates_into_chunks():
    text = "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five."
    # max_tokens=4 强制每句单独成块(每句约 5 token 用近似,fallback 时 1 token≈4 chars)
    chunks = chunk_text(text, max_tokens=4)
    assert len(chunks) >= 2
    assert all(c.chunk_index == i for i, c in enumerate(chunks))


def test_chunk_text_chunk_index_starts_at_zero_and_increments():
    text = "A. B. C. D. E. F. G. H."
    chunks = chunk_text(text, max_tokens=10)
    assert all(c.chunk_index == i for i, c in enumerate(chunks))


def test_chunk_text_long_single_sentence_becomes_its_own_chunk():
    long_sentence = "word " * 200  # ~200 words
    chunks = chunk_text(long_sentence.strip(), max_tokens=50)
    assert len(chunks) >= 1
    # 至少包含原始内容
    assert "word" in chunks[0].content


def test_count_tokens_returns_positive_int():
    n = count_tokens("Hello world")
    assert isinstance(n, int)
    assert n > 0


def test_count_tokens_empty_string():
    assert count_tokens("") >= 0  # tiktoken 可能为 0,我们 max(1, ...) 仅对 fallback


# ---------- InMemoryVectorStore ----------


@pytest.mark.asyncio
async def test_in_memory_vector_store_search_returns_sorted_results(db_session):
    """端到端: 写入分块 -> 检索 -> 按 score 降序。"""
    from db.models import DocumentChunkORM, DocumentORM

    document = DocumentORM(
        title="Test Doc",
        source_type="text",
        content_hash="abc123",
        status="indexed",
    )
    db_session.add(document)
    await db_session.flush()

    chunks = [
        DocumentChunkORM(
            document_id=document.id,
            chunk_index=0,
            content="勾股定理说直角三角形两直角边平方和等于斜边平方",
            embedding=[1.0, 0.0, 0.0],
            token_count=20,
            metadata_={"source_type": "text"},
        ),
        DocumentChunkORM(
            document_id=document.id,
            chunk_index=1,
            content="今天天气真好适合出去玩",
            embedding=[0.0, 1.0, 0.0],
            token_count=15,
            metadata_={"source_type": "text"},
        ),
        DocumentChunkORM(
            document_id=document.id,
            chunk_index=2,
            content="直角三角形的三边关系",
            embedding=[0.9, 0.1, 0.0],
            token_count=12,
            metadata_={"source_type": "text"},
        ),
    ]
    for c in chunks:
        db_session.add(c)
    await db_session.flush()

    store = InMemoryVectorStore(db_session)
    # 查询向量接近 [1,0,0](勾股定理)
    results = await store.search([1.0, 0.0, 0.0], top_k=3, min_score=0.0)

    assert len(results) >= 2
    # 最相似应是 chunk 0(完全匹配)
    assert results[0].chunk_id == chunks[0].id
    assert results[0].score == pytest.approx(1.0, abs=1e-6)
    # 按 score 降序
    for i in range(len(results) - 1):
        assert results[i].score >= results[i + 1].score


@pytest.mark.asyncio
async def test_in_memory_vector_store_search_filters_by_min_score(db_session):
    from db.models import DocumentChunkORM, DocumentORM

    document = DocumentORM(title="t", source_type="text", content_hash="h", status="indexed")
    db_session.add(document)
    await db_session.flush()

    db_session.add(
        DocumentChunkORM(
            document_id=document.id,
            chunk_index=0,
            content="a",
            embedding=[1.0, 0.0],
            token_count=1,
            metadata_={},
        )
    )
    db_session.add(
        DocumentChunkORM(
            document_id=document.id,
            chunk_index=1,
            content="b",
            embedding=[0.0, 1.0],
            token_count=1,
            metadata_={},
        )
    )
    await db_session.flush()

    store = InMemoryVectorStore(db_session)
    # 查 [1,0] 时,只有第一个 chunk 相似度=1,另一个=0
    results = await store.search([1.0, 0.0], top_k=10, min_score=0.5)
    assert len(results) == 1
    assert results[0].content == "a"


@pytest.mark.asyncio
async def test_in_memory_vector_store_search_top_k_limits(db_session):
    from db.models import DocumentChunkORM, DocumentORM

    document = DocumentORM(title="t", source_type="text", content_hash="h", status="indexed")
    db_session.add(document)
    await db_session.flush()

    for i in range(5):
        db_session.add(
            DocumentChunkORM(
                document_id=document.id,
                chunk_index=i,
                content=f"chunk_{i}",
                embedding=[1.0, 0.0],
                token_count=2,
                metadata_={},
            )
        )
    await db_session.flush()

    store = InMemoryVectorStore(db_session)
    results = await store.search([1.0, 0.0], top_k=2, min_score=0.5)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_in_memory_vector_store_invalidate_clears_cache(db_session):
    from db.models import DocumentChunkORM, DocumentORM

    document = DocumentORM(title="t", source_type="text", content_hash="h", status="indexed")
    db_session.add(document)
    await db_session.flush()
    db_session.add(
        DocumentChunkORM(
            document_id=document.id,
            chunk_index=0,
            content="a",
            embedding=[1.0],
            token_count=1,
            metadata_={},
        )
    )
    await db_session.flush()

    store = InMemoryVectorStore(db_session)
    await store.search([1.0], top_k=1)
    assert store._cache is not None

    store.invalidate()
    assert store._cache is None
