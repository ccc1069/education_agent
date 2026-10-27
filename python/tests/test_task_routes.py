"""任务调度管理 API 集成测试: /api/v1/admin/tasks/*。

覆盖:
- 权限: 仅管理员可访问,学生/教师 403
- GET /admin/tasks: 列出已注册任务 + 队列状态
- GET /admin/tasks/history: 任务执行历史
- POST /admin/tasks/trigger/{name}: 手动触发(异步入队)
- POST /admin/tasks/{name}/run: 同步执行
- GET /admin/tasks/queue/stats: 队列统计
- GET /admin/tasks/queue/dead-letters: 死信列表
- 404: 未知任务名
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_list_tasks_requires_admin(client, auth_headers, teacher_headers):
    """非管理员访问 /admin/tasks 返回 403。"""
    r = await client.get("/api/v1/admin/tasks", headers=auth_headers)
    assert r.status_code == 403
    r = await client.get("/api/v1/admin/tasks", headers=teacher_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_list_tasks_returns_registered_tasks(client, admin_headers):
    """管理员能获取任务列表 + 队列统计。"""
    r = await client.get("/api/v1/admin/tasks", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert "registered" in body
    assert "queue_stats" in body
    registered_names = {t["name"] for t in body["registered"]}
    expected = {
        "execute_pending_deletions",
        "send_review_reminders",
        "cleanup_expired_tokens",
        "generate_daily_stats",
    }
    assert expected.issubset(registered_names)
    # 每个任务都有 description + category
    for task in body["registered"]:
        assert "description" in task
        assert "category" in task


@pytest.mark.asyncio
async def test_list_task_history_requires_admin(client, auth_headers):
    r = await client.get("/api/v1/admin/tasks/history", headers=auth_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_list_task_history_returns_list(client, admin_headers):
    """管理员能查询任务执行历史(空列表也 OK)。"""
    r = await client.get("/api/v1/admin/tasks/history", headers=admin_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_list_task_history_with_filters(client, admin_headers):
    """支持 limit/status 等过滤参数。"""
    r = await client.get(
        "/api/v1/admin/tasks/history",
        params={"limit": 10, "status": "success"},
        headers=admin_headers,
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_trigger_task_requires_admin(client, auth_headers):
    r = await client.post(
        "/api/v1/admin/tasks/trigger/cleanup_expired_tokens",
        headers=auth_headers,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_trigger_task_unknown_returns_404(client, admin_headers):
    """触发不存在的任务返回 404。"""
    r = await client.post(
        "/api/v1/admin/tasks/trigger/nonexistent_task",
        headers=admin_headers,
    )
    assert r.status_code == 404
    assert "not registered" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_trigger_task_enqueue_success(client, admin_headers):
    """触发已注册任务应执行并写入历史。"""
    r = await client.post(
        "/api/v1/admin/tasks/trigger/cleanup_expired_tokens",
        headers=admin_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["task_name"] == "cleanup_expired_tokens"
    assert body["status"] in {"success", "failed"}

    hist = await client.get(
        "/api/v1/admin/tasks/history?task_name=cleanup_expired_tokens&limit=1",
        headers=admin_headers,
    )
    assert hist.status_code == 200
    rows = hist.json()
    assert len(rows) >= 1
    assert rows[0]["task_name"] == "cleanup_expired_tokens"
    assert rows[0]["triggered_by"].startswith("manual:")


@pytest.mark.asyncio
async def test_run_task_sync_requires_admin(client, auth_headers):
    r = await client.post(
        "/api/v1/admin/tasks/cleanup_expired_tokens/run",
        headers=auth_headers,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_run_task_sync_unknown_returns_404(client, admin_headers):
    r = await client.post(
        "/api/v1/admin/tasks/nonexistent_task/run",
        headers=admin_headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_run_task_sync_executes(client, admin_headers):
    """同步执行任务应返回成功结果。"""
    r = await client.post(
        "/api/v1/admin/tasks/cleanup_expired_tokens/run",
        headers=admin_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["task_name"] == "cleanup_expired_tokens"
    assert body["status"] == "success"
    assert body["result"] is not None
    assert "deleted_tokens" in body["result"]


@pytest.mark.asyncio
async def test_run_task_sync_returns_stats_for_daily(client, admin_headers):
    """同步执行 generate_daily_stats 返回统计字段。"""
    r = await client.post(
        "/api/v1/admin/tasks/generate_daily_stats/run",
        headers=admin_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    result = body["result"]
    assert "date" in result
    assert "active_learners" in result
    assert "total_submissions" in result
    assert "total_audit_logs" in result


@pytest.mark.asyncio
async def test_get_queue_stats_requires_admin(client, auth_headers):
    r = await client.get("/api/v1/admin/tasks/queue/stats", headers=auth_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_get_queue_stats_returns_dict(client, admin_headers):
    """管理员能查询队列实时统计。"""
    r = await client.get("/api/v1/admin/tasks/queue/stats", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    expected_keys = {"enqueued", "succeeded", "failed", "retried", "queue_size"}
    assert expected_keys.issubset(body.keys())


@pytest.mark.asyncio
async def test_get_dead_letters_requires_admin(client, auth_headers):
    r = await client.get(
        "/api/v1/admin/tasks/queue/dead-letters", headers=auth_headers
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_get_dead_letters_returns_list(client, admin_headers):
    """管理员能查询死信队列(初始为空列表)。"""
    r = await client.get(
        "/api/v1/admin/tasks/queue/dead-letters", headers=admin_headers
    )
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_unauthenticated_request_returns_401(client):
    """无 token 访问管理 API 返回 401。"""
    r = await client.get("/api/v1/admin/tasks")
    assert r.status_code == 401
    r = await client.get("/api/v1/admin/tasks/history")
    assert r.status_code == 401
    r = await client.get("/api/v1/admin/tasks/queue/stats")
    assert r.status_code == 401
