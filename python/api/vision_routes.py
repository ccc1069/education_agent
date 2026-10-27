"""Vision Tutor 路由(P2#16c 多模态输入)。

权限:
- 所有学生/教师/管理员可访问(需登录)
- 学生只能用自己的 learner_public_id

接口:
- POST /api/v1/vision/analyze  上传图片 + 文字说明,返回教学引导
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from auth import CurrentUser, get_current_active_user, require_student
from llm.provider import LLMUnavailableError
from llm.vision_service import VisionInputError, VisionTutorService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vision", tags=["vision"])


# ---------- Pydantic 请求模型 ----------


class VisionAnalyzeRequest(BaseModel):
    """视觉分析请求。

    images: data URL 列表(data:image/png;base64,...)或 http(s) URL 列表
    knowledge_id: 学生当前学习的知识点
    learner_message: 学生附加的文字说明(可选)
    level: 学生水平(beginner/developing/proficient/mastered)
    mastery: 学生当前掌握度(0.0-1.0)
    """

    images: list[str] = Field(
        min_length=1,
        max_length=4,
        description="图片 data URL 或 http URL 列表,1-4 张",
    )
    knowledge_id: str = Field(default="general", max_length=64)
    learner_message: str = Field(default="", max_length=500)
    level: str = Field(default="beginner")
    mastery: float = Field(default=0.0, ge=0.0, le=1.0)


class VisionAnalyzeResponse(BaseModel):
    """视觉分析响应。"""

    response: str
    metadata: dict[str, Any]


# ---------- 路由 ----------


@router.post(
    "/analyze",
    response_model=VisionAnalyzeResponse,
    status_code=status.HTTP_200_OK,
)
async def analyze_image(
    req: VisionAnalyzeRequest,
    current: CurrentUser = Depends(get_current_active_user),
    request: Request = None,
):
    """分析图片并生成教学引导。

    - 学生/教师/管理员均可访问(需登录)
    - 学生建议传自己的 learner_public_id 关联(此处用 current.learner_public_id)
    - 图片格式: data:image/(png|jpeg|webp|gif);base64,... 或 http(s):// URL
    - 单张图片 ≤ 4MB,单次最多 4 张
    """
    service = VisionTutorService()

    try:
        response_text, meta = await service.analyze_image(
            knowledge_id=req.knowledge_id,
            level=req.level,
            mastery=req.mastery,
            images=req.images,
            learner_message=req.learner_message,
        )
    except VisionInputError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid image input: {e}",
        )
    except LLMUnavailableError as e:
        # provider 不支持 vision 或 LLM 不可用
        logger.warning("Vision analyze LLM unavailable: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Vision service unavailable: {e}",
        )

    return VisionAnalyzeResponse(response=response_text, metadata=meta)
