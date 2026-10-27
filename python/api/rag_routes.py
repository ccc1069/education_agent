"""RAG 知识库路由: 文档摄取 + 检索。

权限:
- 上传文档: 教师/管理员
- 检索: 所有认证用户(含学生)
- 删除/列表/详情: 所有认证用户
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser, get_current_active_user
from db.models import UserRole
from db.session import get_session_dep
from services import RAGService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge-base", tags=["rag"])


# ---------- Pydantic 请求模型 ----------


class UploadDocumentRequest(BaseModel):
    """文档上传请求(简化: 直接传文本)。"""

    title: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1, max_length=100_000)
    source_type: str = Field(default="text", max_length=32)
    source_url: str | None = Field(default=None, max_length=512)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    min_score: float = Field(default=0.7, ge=0.0, le=1.0)


class DocumentResponse(BaseModel):
    id: int
    title: str
    source_type: str
    source_url: str | None
    status: str
    total_chunks: int
    content_hash: str | None
    created_at: str | None
    error_message: str | None


class DocumentDetailResponse(DocumentResponse):
    metadata: dict[str, Any]
    updated_at: str | None
    chunks: list[dict[str, Any]] = Field(default_factory=list)


class ScoredChunkResponse(BaseModel):
    chunk_id: int
    document_id: int
    content: str
    score: float
    chunk_index: int
    token_count: int
    metadata: dict[str, Any]
    document_title: str | None
    document_source_type: str | None


# ---------- 权限检查 ----------


def _require_staff(current: CurrentUser) -> None:
    """教师/管理员才能上传。"""
    if current.role not in (UserRole.TEACHER, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers and admins can upload documents",
        )


# ---------- 路由 ----------


@router.post(
    "/documents",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    req: UploadDocumentRequest,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """上传文档到知识库(教师/管理员)。"""
    _require_staff(current)
    service = RAGService(session)
    try:
        document_id, is_new = await service.ingest_document(
            title=req.title,
            content=req.content,
            source_type=req.source_type,
            source_url=req.source_url,
            metadata=req.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "document_id": document_id,
        "is_new": is_new,
        "message": "Document uploaded and indexed"
        if is_new
        else "Document already exists (deduplicated)",
    }


@router.get("/documents", response_model=list[DocumentResponse])
async def list_documents(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """列出文档(所有认证用户)。"""
    service = RAGService(session)
    docs = await service.list_documents(status=status_filter, limit=limit, offset=offset)
    return docs


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: int,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """获取单个文档详情。"""
    service = RAGService(session)
    doc = await service.get_document(document_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return doc


@router.post("/documents/{document_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: int,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """删除文档(教师/管理员)。"""
    _require_staff(current)
    service = RAGService(session)
    deleted = await service.delete_document(document_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return None


@router.post("/search", response_model=list[ScoredChunkResponse])
async def search(
    req: SearchRequest,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """检索知识库(所有认证用户)。

    用法:
        POST /api/v1/knowledge-base/search
        {"query": "什么是勾股定理?", "top_k": 5, "min_score": 0.7}
    """
    service = RAGService(session)
    results = await service.search(
        query=req.query,
        top_k=req.top_k,
        min_score=req.min_score,
    )
    return [
        ScoredChunkResponse(
            chunk_id=r.chunk_id,
            document_id=r.document_id,
            content=r.content,
            score=round(r.score, 4),
            chunk_index=r.chunk_index,
            token_count=r.token_count,
            metadata=r.metadata,
            document_title=r.document_title,
            document_source_type=r.document_source_type,
        )
        for r in results
    ]
