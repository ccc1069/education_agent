"""RAGService 端到端测试: ingest -> search -> delete。"""

import pytest

from rag import MockEmbeddingProvider
from services import RAGService


@pytest.fixture
def mock_embedding():
    return MockEmbeddingProvider()


@pytest.mark.asyncio
async def test_rag_service_ingest_document_creates_document_and_chunks(
    db_session, mock_embedding
):
    service = RAGService(db_session, embedding_provider=mock_embedding)
    content = (
        "勾股定理说,直角三角形两直角边的平方和等于斜边的平方。"
        "例如,直角边为 3 和 4 时,斜边为 5。"
        "这是因为 3 的平方加 4 的平方等于 9 加 16 等于 25,而 5 的平方也等于 25。"
    )
    doc_id, is_new = await service.ingest_document(
        title="勾股定理入门",
        content=content,
        source_type="text",
    )
    assert doc_id > 0
    assert is_new is True

    # 验证文档落库
    detail = await service.get_document(doc_id)
    assert detail["title"] == "勾股定理入门"
    assert detail["status"] == "indexed"
    assert detail["total_chunks"] >= 1


@pytest.mark.asyncio
async def test_rag_service_ingest_document_deduplicates_by_content_hash(
    db_session, mock_embedding
):
    service = RAGService(db_session, embedding_provider=mock_embedding)
    content = "Same content. Should dedupe."
    doc_id_1, is_new_1 = await service.ingest_document(
        title="First", content=content
    )
    doc_id_2, is_new_2 = await service.ingest_document(
        title="Second", content=content
    )
    assert doc_id_1 == doc_id_2
    assert is_new_1 is True
    assert is_new_2 is False


@pytest.mark.asyncio
async def test_rag_service_ingest_rejects_empty_content(db_session, mock_embedding):
    service = RAGService(db_session, embedding_provider=mock_embedding)
    with pytest.raises(ValueError, match="cannot be empty"):
        await service.ingest_document(title="empty", content="")


@pytest.mark.asyncio
async def test_rag_service_search_returns_relevant_chunks(db_session, mock_embedding):
    """摄取文档后,检索应能返回相关片段。"""
    service = RAGService(db_session, embedding_provider=mock_embedding)
    content = (
        "勾股定理是关于直角三角形的基本定理。"
        "它说明两直角边的平方和等于斜边的平方。"
        "这是古希腊数学家毕达哥拉斯发现的。"
    )
    await service.ingest_document(title="勾股定理", content=content)

    # 检索相关查询
    results = await service.search(query="勾股定理 直角三角形", top_k=5, min_score=0.0)
    assert len(results) >= 1
    assert results[0].content  # 有内容
    assert results[0].document_title == "勾股定理"


@pytest.mark.asyncio
async def test_rag_service_search_empty_query_returns_empty(db_session, mock_embedding):
    service = RAGService(db_session, embedding_provider=mock_embedding)
    results = await service.search(query="", top_k=5, min_score=0.0)
    assert results == []


@pytest.mark.asyncio
async def test_rag_service_search_min_score_filters_out_low_quality(
    db_session, mock_embedding
):
    service = RAGService(db_session, embedding_provider=mock_embedding)
    await service.ingest_document(title="math", content="勾股定理 直角三角形 斜边")
    # 设置很高的 min_score,应过滤掉所有结果(Mock 不保证高相似度)
    results = await service.search(query="天气", top_k=5, min_score=0.99)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_rag_service_delete_document_removes_chunks(db_session, mock_embedding):
    service = RAGService(db_session, embedding_provider=mock_embedding)
    doc_id, _ = await service.ingest_document(
        title="to delete", content="Some content to be deleted later."
    )

    # 验证有 chunks
    detail = await service.get_document(doc_id)
    assert detail["total_chunks"] >= 1

    deleted = await service.delete_document(doc_id)
    assert deleted is True

    # 验证文档已删
    detail = await service.get_document(doc_id)
    assert detail is None


@pytest.mark.asyncio
async def test_rag_service_delete_nonexistent_returns_false(db_session, mock_embedding):
    service = RAGService(db_session, embedding_provider=mock_embedding)
    deleted = await service.delete_document(99999)
    assert deleted is False


@pytest.mark.asyncio
async def test_rag_service_list_documents(db_session, mock_embedding):
    service = RAGService(db_session, embedding_provider=mock_embedding)
    await service.ingest_document(title="doc1", content="content one")
    await service.ingest_document(title="doc2", content="content two")
    await service.ingest_document(title="doc3", content="content three")

    docs = await service.list_documents(limit=10)
    assert len(docs) == 3
    # 按创建时间倒序,最新在前
    assert docs[0]["title"] == "doc3"


@pytest.mark.asyncio
async def test_rag_service_list_documents_filters_by_status(db_session, mock_embedding):
    service = RAGService(db_session, embedding_provider=mock_embedding)
    await service.ingest_document(title="ok1", content="content one")
    await service.ingest_document(title="ok2", content="content two")

    docs = await service.list_documents(status="indexed")
    assert all(d["status"] == "indexed" for d in docs)
    assert len(docs) == 2


@pytest.mark.asyncio
async def test_rag_service_search_after_delete_returns_empty(db_session, mock_embedding):
    """删除文档后,检索不应再返回该文档的片段。"""
    service = RAGService(db_session, embedding_provider=mock_embedding)
    doc_id, _ = await service.ingest_document(
        title="temp", content="勾股定理 直角三角形 斜边平方"
    )

    # 先验证可搜到
    results_before = await service.search(query="勾股定理", top_k=5, min_score=0.0)
    assert len(results_before) >= 1

    await service.delete_document(doc_id)

    # 删除后不应再搜到
    results_after = await service.search(query="勾股定理", top_k=5, min_score=0.0)
    assert all(r.document_id != doc_id for r in results_after)
