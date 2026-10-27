"""Vision Tutor 服务: 多模态图像输入 + 教学引导(P2#16c)。

设计:
- analyze_image(): 接受图片(data URL 或 http URL) + 文字说明,
  调 LLM Vision 分析题目并给出教学引导
- 支持 PNG/JPEG/WebP data URL
- provider 不支持 vision 时返回明确错误(不静默降级)
- LLM 不可用时抛 LLMUnavailableError(调用方决定 503 还是降级)
"""

import base64
import logging
import re
import struct
from typing import Any

from llm.factory import get_vision_llm_provider
from llm.prompts import VISION_TUTOR_SYSTEM_PROMPT, build_vision_tutor_user_prompt
from llm.provider import (
    LLMError,
    LLMMessage,
    LLMProvider,
    LLMRole,
    LLMUnavailableError,
)

logger = logging.getLogger(__name__)

# 支持的图片 MIME 类型
SUPPORTED_IMAGE_MIME = ("image/png", "image/jpeg", "image/webp", "image/gif")

# 单张图片大小上限(data URL 解码后,4MB)
MAX_IMAGE_BYTES = 4 * 1024 * 1024

# 通义 VL 等要求边长 > 10
MIN_IMAGE_SIDE = 11

# 单次最多图片数
MAX_IMAGES_PER_REQUEST = 4

_DATA_URL_RE = re.compile(r"^data:(image/[a-z+]+);base64,(.+)$", re.DOTALL)


class VisionInputError(Exception):
    """图片输入不合法(格式/大小/数量)。"""


def validate_data_url(data_url: str) -> None:
    """校验 data URL 格式 + 大小。"""
    if not data_url or not isinstance(data_url, str):
        raise VisionInputError("image data URL is empty")
    m = _DATA_URL_RE.match(data_url)
    if not m:
        raise VisionInputError(
            "invalid data URL, expected 'data:image/<type>;base64,<...>'"
        )
    mime, b64 = m.group(1), m.group(2)
    if mime not in SUPPORTED_IMAGE_MIME:
        raise VisionInputError(
            f"unsupported image MIME: {mime}, supported: {SUPPORTED_IMAGE_MIME}"
        )
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception as e:
        raise VisionInputError(f"invalid base64 encoding: {e}") from e
    if len(raw) > MAX_IMAGE_BYTES:
        raise VisionInputError(
            f"image too large: {len(raw)} bytes, max {MAX_IMAGE_BYTES}"
        )
    _check_min_dimensions(raw, mime)


def _check_min_dimensions(raw: bytes, mime: str) -> None:
    """尽量用标准库读取宽高,过小则提前拒绝(避免 VL 模型 400)。"""
    w = h = None
    if mime == "image/png" and raw.startswith(b"\x89PNG") and len(raw) >= 24:
        w, h = struct.unpack(">II", raw[16:24])
    if w is not None and h is not None and (w < MIN_IMAGE_SIDE or h < MIN_IMAGE_SIDE):
        raise VisionInputError(
            f"image too small: {w}x{h}, each side must be >= {MIN_IMAGE_SIDE}"
        )


def validate_http_url(url: str) -> None:
    """校验 http(s) URL(只做协议检查,不下载)。"""
    if not url or not isinstance(url, str):
        raise VisionInputError("image URL is empty")
    if not url.startswith(("http://", "https://")):
        raise VisionInputError(
            f"unsupported image URL scheme, expected http/https: {url[:50]!r}"
        )


def validate_images(images: list[str]) -> None:
    """校验图片列表(数量 + 每张格式)。"""
    if not images:
        raise VisionInputError("no images provided")
    if len(images) > MAX_IMAGES_PER_REQUEST:
        raise VisionInputError(
            f"too many images: {len(images)}, max {MAX_IMAGES_PER_REQUEST}"
        )
    for i, img in enumerate(images):
        if img.startswith("data:"):
            validate_data_url(img)
        else:
            validate_http_url(img)


class VisionTutorService:
    """多模态视觉教学服务。

    用法:
        service = VisionTutorService()
        response_text, meta = await service.analyze_image(
            knowledge_id="geometry",
            level="beginner",
            mastery=0.3,
            images=["data:image/png;base64,iVBOR..."],
            learner_message="这道题我不会做",
        )
    """

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider or get_vision_llm_provider()

    async def analyze_image(
        self,
        knowledge_id: str,
        level: str,
        mastery: float,
        images: list[str],
        learner_message: str = "",
    ) -> tuple[str, dict[str, Any]]:
        """分析图片并生成教学引导。返回 (response_text, metadata)。

        Raises:
            VisionInputError: 图片不合法
            LLMUnavailableError: provider 不支持 vision 或 LLM 不可用
        """
        validate_images(images)

        if not self.provider.supports_vision:
            raise LLMUnavailableError(
                f"provider {self.provider.name} (model={self.provider.model}) "
                "does not support vision input"
            )

        system_prompt = VISION_TUTOR_SYSTEM_PROMPT
        user_prompt = build_vision_tutor_user_prompt(
            knowledge_id, level, mastery, learner_message
        )

        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content=system_prompt),
            LLMMessage(role=LLMRole.USER, content=user_prompt, images=images),
        ]

        try:
            response = await self.provider.complete(
                messages, temperature=0.5, max_tokens=400
            )
        except LLMUnavailableError:
            raise
        except LLMError as e:
            raise LLMUnavailableError(f"vision LLM call failed: {e}") from e

        metadata = {
            "llm_used": True,
            "model": response.model,
            "tokens": response.total_tokens,
            "latency_ms": response.latency_ms,
            "vision": True,
            "image_count": len(images),
        }
        return response.content, metadata
