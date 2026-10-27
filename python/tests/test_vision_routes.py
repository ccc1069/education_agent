"""Vision 路由集成测试: POST /api/v1/vision/analyze。

覆盖:
- 未登录 401
- 合法 data URL 图片 200 + 教学引导
- 多张图片 200
- 空 images 列表 422
- 不支持的 MIME 422
- http URL 图片 200
"""

import base64

import pytest
from httpx import AsyncClient


def _make_data_url(mime: str = "image/png", payload: bytes = b"\x89PNG\r\n\x1a\n") -> str:
    b64 = base64.b64encode(payload).decode("ascii")
    return f"data:{mime};base64,{b64}"


@pytest.mark.asyncio
async def test_vision_analyze_unauthorized(client: AsyncClient):
    """未登录应返回 401。"""
    r = await client.post(
        "/api/v1/vision/analyze",
        json={"images": [_make_data_url()]},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_vision_analyze_with_data_url(client: AsyncClient, auth_headers):
    """合法 data URL 图片应返回 200 + 教学引导。"""
    r = await client.post(
        "/api/v1/vision/analyze",
        headers=auth_headers,
        json={
            "images": [_make_data_url("image/png")],
            "knowledge_id": "geometry",
            "level": "beginner",
            "mastery": 0.3,
            "learner_message": "这道题我不会做",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "response" in body
    assert "metadata" in body
    assert body["metadata"]["llm_used"] is True
    assert body["metadata"]["vision"] is True
    assert body["metadata"]["image_count"] == 1
    assert "Mock 视觉分析" in body["response"]  # MockLLMProvider 返回


@pytest.mark.asyncio
async def test_vision_analyze_multiple_images(client: AsyncClient, auth_headers):
    """多张图片应返回 200。"""
    r = await client.post(
        "/api/v1/vision/analyze",
        headers=auth_headers,
        json={
            "images": [
                _make_data_url("image/png"),
                _make_data_url("image/jpeg"),
                _make_data_url("image/webp"),
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["metadata"]["image_count"] == 3


@pytest.mark.asyncio
async def test_vision_analyze_http_url(client: AsyncClient, auth_headers):
    """http URL 图片应返回 200(Mock 不实际下载)。"""
    r = await client.post(
        "/api/v1/vision/analyze",
        headers=auth_headers,
        json={"images": ["https://example.com/problem.png"]},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_vision_analyze_empty_images_rejected(client: AsyncClient, auth_headers):
    """空 images 列表应被 Pydantic 拒绝(422)。"""
    r = await client.post(
        "/api/v1/vision/analyze",
        headers=auth_headers,
        json={"images": []},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_vision_analyze_too_many_images_rejected(client: AsyncClient, auth_headers):
    """超过 4 张图片应被 Pydantic 拒绝(422)。"""
    r = await client.post(
        "/api/v1/vision/analyze",
        headers=auth_headers,
        json={"images": [_make_data_url() for _ in range(5)]},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_vision_analyze_invalid_mime_rejected(client: AsyncClient, auth_headers):
    """不支持的 MIME 应返回 422。"""
    r = await client.post(
        "/api/v1/vision/analyze",
        headers=auth_headers,
        json={"images": [_make_data_url("image/bmp")]},
    )
    assert r.status_code == 422
    assert "Invalid image input" in r.json()["detail"]


@pytest.mark.asyncio
async def test_vision_analyze_invalid_data_url_rejected(client: AsyncClient, auth_headers):
    """非法 data URL 格式应返回 422。"""
    r = await client.post(
        "/api/v1/vision/analyze",
        headers=auth_headers,
        json={"images": ["not a valid url"]},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_vision_analyze_admin_can_access(client: AsyncClient, admin_headers):
    """管理员也可访问 vision 接口。"""
    r = await client.post(
        "/api/v1/vision/analyze",
        headers=admin_headers,
        json={"images": [_make_data_url()]},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_vision_analyze_teacher_can_access(client: AsyncClient, teacher_headers):
    """教师也可访问 vision 接口。"""
    r = await client.post(
        "/api/v1/vision/analyze",
        headers=teacher_headers,
        json={"images": [_make_data_url()]},
    )
    assert r.status_code == 200
