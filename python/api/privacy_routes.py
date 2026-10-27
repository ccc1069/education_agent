"""数据合规与隐私路由: 同意管理 + 数据导出 + 账户删除 + 审计日志查询。

权限:
- 同意/导出/删除: 用户自己操作自己的数据(已认证即可)
- 审计日志查询: 仅管理员
- 审计写入: 所有敏感操作自动记录(由服务层调用 AuditService)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth import CurrentUser, get_current_active_user
from db.models import UserRole
from db.session import get_session_dep
from api.audit_helpers import client_ip, client_ua, write_audit
from services import AuditService, PrivacyService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/privacy", tags=["privacy"])
audit_router = APIRouter(prefix="/audit", tags=["audit"])


# ---------- Pydantic 模型 ----------


class SetConsentRequest(BaseModel):
    """设置同意请求。"""

    consent_type: str = Field(
        description="analytics / llm_training / marketing / third_party_share"
    )
    granted: bool


class RequestDeletionRequest(BaseModel):
    """账户删除请求。"""

    reason: str = Field(default="", max_length=1000)


class ConsentInfo(BaseModel):
    consent_type: str
    granted: bool
    consent_version: str
    created_at: str | None


class ConsentStatus(BaseModel):
    analytics: bool
    llm_training: bool
    marketing: bool
    third_party_share: bool


class DeletionRequestInfo(BaseModel):
    id: int
    user_id: int
    status: str
    requested_at: str | None
    scheduled_at: str | None
    completed_at: str | None
    cancelled_at: str | None
    reason: str


class ExportJobInfo(BaseModel):
    id: int
    user_id: int
    status: str
    requested_at: str | None
    completed_at: str | None
    download_url: str | None
    file_size_bytes: int
    error_message: str | None


class AuditLogInfo(BaseModel):
    id: int
    actor: str
    action: str
    target: str
    ip: str
    user_agent: str
    metadata: dict[str, Any]
    created_at: str | None
    prev_hash: str
    curr_hash: str


class ChainVerificationResult(BaseModel):
    valid: bool
    checked: int
    broken_at: int | None


# ---------- 辅助 ----------


def _require_admin(current: CurrentUser) -> None:
    if current.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can access audit logs",
        )


# ---------- 同意管理 ----------


@router.get("/consent", response_model=ConsentStatus)
async def get_consent_status(
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """获取当前用户的所有同意状态(默认全 False)。"""
    service = PrivacyService(session)
    status_dict = await service.get_consent_status(current.id)
    return status_dict


@router.post("/consent", response_model=ConsentInfo)
async def set_consent(
    req: SetConsentRequest,
    request: Request,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """设置某项同意(追加写,不可修改历史)。"""
    service = PrivacyService(session)
    try:
        result = await service.set_consent(
            user_id=current.id,
            consent_type=req.consent_type,
            granted=req.granted,
            ip=client_ip(request),
            user_agent=client_ua(request),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    await write_audit(
        session,
        actor=current.email,
        action="consent_set",
        target=f"user:{current.id}:consent:{req.consent_type}",
        request=request,
        metadata={"granted": req.granted},
    )
    return result


# ---------- 数据导出 ----------


@router.post("/export", response_model=ExportJobInfo, status_code=status.HTTP_201_CREATED)
async def request_data_export(
    request: Request,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """请求导出个人全部数据(GDPR/PIPL 数据可携带权)。

    同步生成(生产环境应改异步),完成后通过 download_url 下载。
    """
    service = PrivacyService(session)
    try:
        result = await service.request_export(current.id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
    await write_audit(
        session,
        actor=current.email,
        action="data_export",
        target=f"user:{current.id}",
        request=request,
        metadata={"job_id": result["id"], "size_bytes": result["file_size_bytes"]},
    )
    return result


@router.get("/export/jobs", response_model=list[ExportJobInfo])
async def list_export_jobs(
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """列出我的导出任务历史。"""
    service = PrivacyService(session)
    return await service.list_export_jobs(current.id)


@router.get("/export/{job_id}/download")
async def download_export(
    job_id: int,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """下载导出的数据(JSON 附件)。"""
    from fastapi.responses import JSONResponse

    service = PrivacyService(session)
    data = await service.get_export_data(job_id, current.id)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export job not found or not completed",
        )
    return JSONResponse(
        content=data,
        headers={
            "Content-Disposition": f'attachment; filename="lumen-export-{job_id}.json"',
        },
    )


# ---------- 账户删除 ----------


@router.post("/delete", response_model=DeletionRequestInfo, status_code=status.HTTP_201_CREATED)
async def request_account_deletion(
    req: RequestDeletionRequest,
    request: Request,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """提交账户删除请求(30 天宽限期)。"""
    service = PrivacyService(session)
    result = await service.request_deletion(current.id, reason=req.reason)
    await write_audit(
        session,
        actor=current.email,
        action="deletion_requested",
        target=f"user:{current.id}",
        request=request,
        metadata={"request_id": result["id"], "scheduled_at": result["scheduled_at"]},
    )
    return result


@router.get("/delete", response_model=DeletionRequestInfo | None)
async def get_deletion_request(
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """查询我的删除请求状态。"""
    service = PrivacyService(session)
    return await service.get_deletion_request(current.id)


@router.post("/delete/cancel", response_model=DeletionRequestInfo)
async def cancel_deletion(
    request: Request,
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """撤销删除请求(宽限期内)。"""
    service = PrivacyService(session)
    try:
        result = await service.cancel_deletion(current.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active deletion request",
        )
    await write_audit(
        session,
        actor=current.email,
        action="deletion_cancelled",
        target=f"user:{current.id}",
        request=request,
        metadata={"request_id": result["id"]},
    )
    return result


# ---------- 审计日志(管理员) ----------


@audit_router.get("/logs", response_model=list[AuditLogInfo])
async def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    actor: str | None = Query(default=None),
    action: str | None = Query(default=None),
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """查询审计日志(仅管理员)。"""
    _require_admin(current)
    service = AuditService(session)
    return await service.list_recent(
        limit=limit, offset=offset, actor=actor, action=action
    )


@audit_router.get("/verify", response_model=ChainVerificationResult)
async def verify_audit_chain(
    from_log_id: int = Query(default=1, ge=1),
    current: CurrentUser = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session_dep),
):
    """验证审计日志 HMAC 链完整性(仅管理员)。"""
    _require_admin(current)
    service = AuditService(session)
    return await service.verify_chain(from_log_id=from_log_id)
