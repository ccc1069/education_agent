"""隐私合规 API 集成测试: 同意 + 导出 + 删除 + 审计查询。"""

import pytest


# ---------- 权限: 未认证 ----------


@pytest.mark.asyncio
async def test_get_consent_requires_auth(client):
    resp = await client.get("/api/v1/privacy/consent")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_set_consent_requires_auth(client):
    resp = await client.post(
        "/api/v1/privacy/consent",
        json={"consent_type": "analytics", "granted": True},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_export_requires_auth(client):
    resp = await client.post("/api/v1/privacy/export")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_deletion_requires_auth(client):
    resp = await client.post("/api/v1/privacy/delete", json={"reason": ""})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_audit_logs_requires_admin(client, auth_headers):
    """学生不能查询审计日志。"""
    resp = await client.get("/api/v1/audit/logs", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_audit_verify_requires_admin(client, auth_headers):
    resp = await client.get("/api/v1/audit/verify", headers=auth_headers)
    assert resp.status_code == 403


# ---------- 同意管理 ----------


@pytest.mark.asyncio
async def test_get_consent_returns_defaults(client, auth_headers):
    resp = await client.get("/api/v1/privacy/consent", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "analytics": False,
        "llm_training": False,
        "marketing": False,
        "third_party_share": False,
    }


@pytest.mark.asyncio
async def test_set_consent_success(client, auth_headers):
    resp = await client.post(
        "/api/v1/privacy/consent",
        json={"consent_type": "analytics", "granted": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["granted"] is True
    assert body["consent_type"] == "analytics"


@pytest.mark.asyncio
async def test_set_consent_rejects_unknown_type(client, auth_headers):
    resp = await client.post(
        "/api/v1/privacy/consent",
        json={"consent_type": "unknown", "granted": True},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_set_consent_records_audit_log(client, auth_headers, admin_headers):
    """同意变更应记录审计日志。"""
    await client.post(
        "/api/v1/privacy/consent",
        json={"consent_type": "marketing", "granted": True},
        headers=auth_headers,
    )

    # 管理员查询审计日志
    resp = await client.get(
        "/api/v1/audit/logs?action=consent_set",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    logs = resp.json()
    assert len(logs) >= 1
    assert logs[0]["action"] == "consent_set"
    assert "consent:marketing" in logs[0]["target"]


# ---------- 数据导出 ----------


@pytest.mark.asyncio
async def test_request_export_success(client, auth_headers):
    resp = await client.post("/api/v1/privacy/export", headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["file_size_bytes"] > 0
    assert body["download_url"]


@pytest.mark.asyncio
async def test_download_export_returns_data(client, auth_headers):
    create = await client.post("/api/v1/privacy/export", headers=auth_headers)
    job_id = create.json()["id"]
    download_url = create.json()["download_url"]

    resp = await client.get(download_url, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "user" in data
    assert "learner" in data
    assert "knowledge_states" in data
    assert "submissions" in data
    assert data["user"]["email"] == "student@test.local"


@pytest.mark.asyncio
async def test_download_other_users_export_returns_404(client, auth_headers, admin_headers):
    """学生想下载管理员的导出 -> 404(归属校验)。"""
    create = await client.post("/api/v1/privacy/export", headers=admin_headers)
    download_url = create.json()["download_url"]

    resp = await client.get(download_url, headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_export_jobs(client, auth_headers):
    await client.post("/api/v1/privacy/export", headers=auth_headers)
    await client.post("/api/v1/privacy/export", headers=auth_headers)

    resp = await client.get("/api/v1/privacy/export/jobs", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ---------- 账户删除 ----------


@pytest.mark.asyncio
async def test_request_deletion_success(client, auth_headers):
    resp = await client.post(
        "/api/v1/privacy/delete",
        json={"reason": "leaving"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["scheduled_at"]
    assert body["reason"] == "leaving"


@pytest.mark.asyncio
async def test_get_deletion_status(client, auth_headers):
    await client.post(
        "/api/v1/privacy/delete",
        json={"reason": ""},
        headers=auth_headers,
    )

    resp = await client.get("/api/v1/privacy/delete", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"


@pytest.mark.asyncio
async def test_cancel_deletion(client, auth_headers):
    await client.post(
        "/api/v1/privacy/delete",
        json={"reason": ""},
        headers=auth_headers,
    )

    resp = await client.post("/api/v1/privacy/delete/cancel", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_without_request_returns_404(client, auth_headers):
    resp = await client.post("/api/v1/privacy/delete/cancel", headers=auth_headers)
    assert resp.status_code == 404


# ---------- 审计日志(管理员) ----------


@pytest.mark.asyncio
async def test_admin_lists_audit_logs(client, admin_headers):
    """触发一些审计事件后管理员能查到。"""
    # 管理员自己的操作(导出)
    await client.post("/api/v1/privacy/export", headers=admin_headers)

    resp = await client.get("/api/v1/audit/logs", headers=admin_headers)
    assert resp.status_code == 200
    logs = resp.json()
    assert len(logs) >= 1
    # 最新在前
    assert logs[0]["action"] in ("data_export", "consent_set")


@pytest.mark.asyncio
async def test_audit_logs_filter_by_action(client, admin_headers, auth_headers):
    """按 action 过滤。"""
    # 学生触发 consent_set + data_export
    await client.post(
        "/api/v1/privacy/consent",
        json={"consent_type": "analytics", "granted": True},
        headers=auth_headers,
    )
    await client.post("/api/v1/privacy/export", headers=auth_headers)

    # 只查 consent_set
    resp = await client.get(
        "/api/v1/audit/logs?action=consent_set",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    logs = resp.json()
    assert all(l["action"] == "consent_set" for l in logs)
    assert len(logs) >= 1


@pytest.mark.asyncio
async def test_audit_chain_verification_passes(client, admin_headers):
    """未篡改的链验证通过。"""
    # 触发几条审计事件
    for _ in range(3):
        await client.post("/api/v1/privacy/export", headers=admin_headers)

    resp = await client.get("/api/v1/audit/verify", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["checked"] >= 3
    assert body["broken_at"] is None


@pytest.mark.asyncio
async def test_audit_log_contains_hash_fields(client, admin_headers):
    """审计日志响应包含 prev_hash + curr_hash 字段。"""
    await client.post("/api/v1/privacy/export", headers=admin_headers)

    resp = await client.get("/api/v1/audit/logs?limit=1", headers=admin_headers)
    assert resp.status_code == 200
    log = resp.json()[0]
    assert "prev_hash" in log
    assert "curr_hash" in log
    assert len(log["curr_hash"]) == 64  # SHA-256 hex
