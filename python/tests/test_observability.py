"""可观测性测试: correlation_id + metrics + health。"""

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_correlation_id_propagated_through_request(app):
    """请求应返回 X-Correlation-ID 头。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert "x-correlation-id" in resp.headers
    assert resp.headers["x-correlation-id"]  # 非空


@pytest.mark.asyncio
async def test_correlation_id_preserved_when_provided(app):
    """若客户端传入 X-Correlation-ID,服务端应沿用。"""
    transport = ASGITransport(app=app)
    custom_id = "my-trace-id-123"
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health", headers={"X-Correlation-ID": custom_id})
    assert resp.headers["x-correlation-id"] == custom_id


@pytest.mark.asyncio
async def test_live_endpoint_returns_ok(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/live")
    assert resp.status_code == 200
    assert resp.json()["alive"] is True


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 先发一个请求,触发 MetricsMiddleware
        await ac.get("/live")
        resp = await ac.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers.get("content-type", "")
    # 至少应该有 http_request_duration_seconds 指标
    body = resp.text
    assert "http_request_duration_seconds" in body or "PROCESS_START_TIME" in body


@pytest.mark.asyncio
async def test_health_endpoint_returns_components(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")
    # /health 不返回 503,只是描述状态
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert "components" in body


def test_correlation_id_contextvar_isolation():
    """contextvar 应在并发任务间隔离。"""
    import asyncio

    from observability.correlation import (
        get_correlation_id,
        set_correlation_id,
    )

    async def task(cid: str) -> str | None:
        set_correlation_id(cid)
        await asyncio.sleep(0.01)
        return get_correlation_id()

    async def main():
        results = await asyncio.gather(
            task("a"), task("b"), task("c")
        )
        return set(results)

    results = asyncio.run(main())
    assert results == {"a", "b", "c"}


def test_metrics_definitions_exist():
    """关键 Prometheus 指标应已定义。"""
    from observability.metrics import (
        ACTIVE_WS_CONNECTIONS,
        AGENT_PROCESSING_DURATION,
        LLM_REQUEST_DURATION,
        LLM_TOKENS_USED,
        REQUEST_DURATION,
    )

    assert REQUEST_DURATION is not None
    assert AGENT_PROCESSING_DURATION is not None
    assert LLM_TOKENS_USED is not None
    assert LLM_REQUEST_DURATION is not None
    assert ACTIVE_WS_CONNECTIONS is not None
