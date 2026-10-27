"""VisionTutorService 单元测试: 多模态图像输入 + 校验 + provider 兼容性。"""

import base64
from typing import Any

import pytest

from llm.mock_provider import MockLLMProvider
from llm.provider import (
    LLMError,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    LLMRole,
    LLMUnavailableError,
)
from llm.vision_service import (
    MAX_IMAGE_BYTES,
    MAX_IMAGES_PER_REQUEST,
    SUPPORTED_IMAGE_MIME,
    VisionInputError,
    VisionTutorService,
    validate_data_url,
    validate_http_url,
    validate_images,
)


# ---------- 测试用 Provider ----------


class _NoVisionProvider(LLMProvider):
    """不支持 vision 的 provider。"""

    def __init__(self) -> None:
        super().__init__(name="text-only", model="text-1.0", timeout=1.0, max_retries=1)

    async def _call(self, messages, **kwargs):
        raise LLMError("should not be called")


class _AlwaysFailsProvider(LLMProvider):
    """总是失败的 provider,但声明支持 vision。"""

    def __init__(self) -> None:
        super().__init__(name="fail", model="gpt-4o", timeout=1.0, max_retries=1)
        self.retry_initial_delay = 0.0

    @property
    def supports_vision(self) -> bool:
        return True

    async def _call(self, messages, **kwargs):
        raise LLMError("simulated failure")


# ---------- data URL 校验 ----------


def _make_data_url(mime: str = "image/png", payload: bytes = b"\x89PNG\r\n\x1a\n") -> str:
    """构造合法的 data URL。"""
    b64 = base64.b64encode(payload).decode("ascii")
    return f"data:{mime};base64,{b64}"


def test_validate_data_url_valid_png():
    validate_data_url(_make_data_url("image/png"))  # 不抛即通过


def test_validate_data_url_valid_jpeg():
    validate_data_url(_make_data_url("image/jpeg"))


def test_validate_data_url_valid_webp():
    validate_data_url(_make_data_url("image/webp"))


def test_validate_data_url_empty_raises():
    with pytest.raises(VisionInputError):
        validate_data_url("")


def test_validate_data_url_invalid_format_raises():
    with pytest.raises(VisionInputError):
        validate_data_url("not a data url")


def test_validate_data_url_unsupported_mime_raises():
    with pytest.raises(VisionInputError) as exc:
        validate_data_url(_make_data_url("image/bmp"))
    assert "unsupported image MIME" in str(exc.value)


def test_validate_data_url_invalid_base64_raises():
    with pytest.raises(VisionInputError):
        validate_data_url("data:image/png;base64,!!!not-base64!!!")


def test_validate_data_url_too_large_raises():
    """图片超过 4MB 限制。"""
    big_payload = b"\x00" * (MAX_IMAGE_BYTES + 1)
    b64 = base64.b64encode(big_payload).decode("ascii")
    url = f"data:image/png;base64,{b64}"
    with pytest.raises(VisionInputError) as exc:
        validate_data_url(url)
    assert "too large" in str(exc.value)


# ---------- http URL 校验 ----------


def test_validate_http_url_valid_https():
    validate_http_url("https://example.com/img.png")


def test_validate_http_url_valid_http():
    validate_http_url("http://example.com/img.png")


def test_validate_http_url_empty_raises():
    with pytest.raises(VisionInputError):
        validate_http_url("")


def test_validate_http_url_wrong_scheme_raises():
    with pytest.raises(VisionInputError):
        validate_http_url("ftp://example.com/img.png")


def test_validate_http_url_no_scheme_raises():
    with pytest.raises(VisionInputError):
        validate_http_url("example.com/img.png")


# ---------- 图片列表校验 ----------


def test_validate_images_empty_list_raises():
    with pytest.raises(VisionInputError):
        validate_images([])


def test_validate_images_too_many_raises():
    urls = [_make_data_url() for _ in range(MAX_IMAGES_PER_REQUEST + 1)]
    with pytest.raises(VisionInputError) as exc:
        validate_images(urls)
    assert "too many images" in str(exc.value)


def test_validate_images_max_allowed_ok():
    urls = [_make_data_url() for _ in range(MAX_IMAGES_PER_REQUEST)]
    validate_images(urls)  # 不抛即通过


def test_validate_images_mixed_data_and_http_ok():
    urls = [_make_data_url(), "https://example.com/img.png"]
    validate_images(urls)


def test_validate_images_invalid_in_list_raises():
    urls = [_make_data_url(), "not a valid url"]
    with pytest.raises(VisionInputError):
        validate_images(urls)


# ---------- VisionTutorService.analyze_image ----------


@pytest.mark.asyncio
async def test_analyze_image_with_mock_provider():
    """MockLLMProvider 支持 vision,正常返回。"""
    service = VisionTutorService(provider=MockLLMProvider())
    response, meta = await service.analyze_image(
        knowledge_id="geometry",
        level="beginner",
        mastery=0.3,
        images=[_make_data_url()],
        learner_message="这道题我不会",
    )
    assert response
    assert "Mock 视觉分析" in response
    assert meta["llm_used"] is True
    assert meta["vision"] is True
    assert meta["image_count"] == 1


@pytest.mark.asyncio
async def test_analyze_image_multiple_images():
    """多张图片应能正常处理。"""
    service = VisionTutorService(provider=MockLLMProvider())
    response, meta = await service.analyze_image(
        knowledge_id="kp1",
        level="beginner",
        mastery=0.5,
        images=[_make_data_url(), _make_data_url("image/jpeg"), _make_data_url("image/webp")],
    )
    assert meta["image_count"] == 3
    assert "3 张图片" in response


@pytest.mark.asyncio
async def test_analyze_image_http_urls():
    """http URL 图片也能传入(provider 决定是否下载)。"""
    service = VisionTutorService(provider=MockLLMProvider())
    response, meta = await service.analyze_image(
        knowledge_id="kp1",
        level="beginner",
        mastery=0.3,
        images=["https://example.com/problem.png"],
    )
    assert meta["image_count"] == 1
    assert meta["llm_used"] is True


@pytest.mark.asyncio
async def test_analyze_image_provider_does_not_support_vision():
    """provider 不支持 vision 时抛 LLMUnavailableError。"""
    service = VisionTutorService(provider=_NoVisionProvider())
    with pytest.raises(LLMUnavailableError) as exc:
        await service.analyze_image(
            knowledge_id="kp1",
            level="beginner",
            mastery=0.3,
            images=[_make_data_url()],
        )
    assert "does not support vision" in str(exc.value)


@pytest.mark.asyncio
async def test_analyze_image_invalid_input_raises_vision_input_error():
    """图片不合法时抛 VisionInputError,不调 LLM。"""
    service = VisionTutorService(provider=MockLLMProvider())
    with pytest.raises(VisionInputError):
        await service.analyze_image(
            knowledge_id="kp1",
            level="beginner",
            mastery=0.3,
            images=[],  # 空
        )


@pytest.mark.asyncio
async def test_analyze_image_invalid_mime_raises():
    service = VisionTutorService(provider=MockLLMProvider())
    with pytest.raises(VisionInputError):
        await service.analyze_image(
            knowledge_id="kp1",
            level="beginner",
            mastery=0.3,
            images=[_make_data_url("image/bmp")],
        )


@pytest.mark.asyncio
async def test_analyze_image_llm_failure_raises_unavailable():
    """LLM 调用失败抛 LLMUnavailableError。"""
    service = VisionTutorService(provider=_AlwaysFailsProvider())
    with pytest.raises(LLMUnavailableError):
        await service.analyze_image(
            knowledge_id="kp1",
            level="beginner",
            mastery=0.3,
            images=[_make_data_url()],
        )


# ---------- LLMMessage.to_dict 多模态格式 ----------


def test_llm_message_to_dict_no_images():
    msg = LLMMessage(role=LLMRole.USER, content="hello")
    d = msg.to_dict()
    assert d == {"role": "user", "content": "hello"}


def test_llm_message_to_dict_with_images():
    msg = LLMMessage(
        role=LLMRole.USER,
        content="analyze this",
        images=["data:image/png;base64,iVBOR=", "https://x.com/y.png"],
    )
    d = msg.to_dict()
    assert d["role"] == "user"
    assert isinstance(d["content"], list)
    assert len(d["content"]) == 3  # 1 text + 2 image_url
    assert d["content"][0] == {"type": "text", "text": "analyze this"}
    assert d["content"][1] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,iVBOR="},
    }
    assert d["content"][2] == {
        "type": "image_url",
        "image_url": {"url": "https://x.com/y.png"},
    }


def test_llm_message_to_dict_with_empty_images_list():
    """images=[] 等同于无 images。"""
    msg = LLMMessage(role=LLMRole.USER, content="hello", images=[])
    d = msg.to_dict()
    assert d == {"role": "user", "content": "hello"}


# ---------- provider supports_vision 属性 ----------


def test_mock_provider_supports_vision():
    assert MockLLMProvider().supports_vision is True


def test_no_vision_provider_does_not_support_vision():
    assert _NoVisionProvider().supports_vision is False


def test_openai_provider_supports_vision_for_gpt4o():
    from llm.openai_provider import OpenAIProvider

    p = OpenAIProvider(model="gpt-4o", api_key="fake")
    assert p.supports_vision is True


def test_openai_provider_supports_vision_for_qwen_vl():
    from llm.openai_provider import OpenAIProvider

    p = OpenAIProvider(model="qwen-vl-plus", api_key="fake")
    assert p.supports_vision is True


def test_openai_provider_does_not_support_vision_for_gpt35():
    from llm.openai_provider import OpenAIProvider

    p = OpenAIProvider(model="gpt-3.5-turbo", api_key="fake")
    assert p.supports_vision is False


# ---------- constants ----------


def test_supported_image_mime_includes_common_types():
    assert "image/png" in SUPPORTED_IMAGE_MIME
    assert "image/jpeg" in SUPPORTED_IMAGE_MIME
    assert "image/webp" in SUPPORTED_IMAGE_MIME


def test_max_images_per_request_is_4():
    assert MAX_IMAGES_PER_REQUEST == 4


def test_max_image_bytes_is_4mb():
    assert MAX_IMAGE_BYTES == 4 * 1024 * 1024
