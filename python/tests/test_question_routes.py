"""题目库 API 集成测试: 生成 + 审核 + 答题校验。"""

import pytest


async def _register_role(client, role: str, email: str) -> str:
    """注册指定角色用户并返回 token。

    conftest 的 admin_headers/auth_headers 是直接签 token,不走注册。
    这里走 register+login,然后用 admin_headers/auth_headers 替代。
    """
    # 简化: 直接用 conftest 的 auth_headers / admin_headers
    raise NotImplementedError("use admin_headers / auth_headers fixtures instead")


# ---------- 权限: 未认证 ----------


@pytest.mark.asyncio
async def test_questions_generate_requires_auth(client):
    resp = await client.post(
        "/api/v1/questions/generate",
        json={
            "knowledge_id": "kp",
            "question_type": "multiple_choice",
            "difficulty": 3,
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_questions_list_requires_auth(client):
    resp = await client.get("/api/v1/questions")
    assert resp.status_code == 401


# ---------- 权限: 学生不能生成/审核/删除 ----------


@pytest.mark.asyncio
async def test_student_cannot_generate_question(client, auth_headers):
    resp = await client.post(
        "/api/v1/questions/generate",
        json={
            "knowledge_id": "kp",
            "question_type": "multiple_choice",
            "difficulty": 3,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_student_cannot_review_question(client, auth_headers):
    resp = await client.post(
        "/api/v1/questions/1/status",
        json={"new_status": "review"},
        headers=auth_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_student_cannot_delete_question(client, auth_headers):
    resp = await client.post(
        "/api/v1/questions/1/delete",
        headers=auth_headers,
    )
    assert resp.status_code == 403


# ---------- 生成 + 列表 + 详情 + 审核 + 答题 ----------


@pytest.mark.asyncio
async def test_admin_generate_question_success(client, admin_headers):
    resp = await client.post(
        "/api/v1/questions/generate",
        json={
            "knowledge_id": "pythagorean",
            "question_type": "multiple_choice",
            "difficulty": 3,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["is_duplicate"] is False
    assert body["question_id"] > 0
    assert body["status"] == "draft"
    assert body["content"]["stem"]
    assert body["answer"]


@pytest.mark.asyncio
async def test_admin_generate_rejects_invalid_type(client, admin_headers):
    resp = await client.post(
        "/api/v1/questions/generate",
        json={
            "knowledge_id": "kp",
            "question_type": "invalid_type",
            "difficulty": 3,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_admin_generate_rejects_invalid_difficulty(client, admin_headers):
    resp = await client.post(
        "/api/v1/questions/generate",
        json={
            "knowledge_id": "kp",
            "question_type": "multiple_choice",
            "difficulty": 99,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 422  # Pydantic 校验


@pytest.mark.asyncio
async def test_list_questions_returns_generated(client, admin_headers):
    await client.post(
        "/api/v1/questions/generate",
        json={
            "knowledge_id": "kp_list",
            "question_type": "multiple_choice",
            "difficulty": 3,
        },
        headers=admin_headers,
    )
    resp = await client.get("/api/v1/questions", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1
    assert body[0]["knowledge_id"] == "kp_list"
    # 列表不返回答案
    assert "answer" not in body[0]


@pytest.mark.asyncio
async def test_get_question_returns_summary_for_student(client, admin_headers, auth_headers):
    gen = await client.post(
        "/api/v1/questions/generate",
        json={
            "knowledge_id": "kp_get",
            "question_type": "multiple_choice",
            "difficulty": 3,
        },
        headers=admin_headers,
    )
    qid = gen.json()["question_id"]

    # 学生访问 draft 题目 -> 403
    resp = await client.get(
        f"/api/v1/questions/{qid}", headers=auth_headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_question_published_visible_to_student(
    client, admin_headers, auth_headers
):
    gen = await client.post(
        "/api/v1/questions/generate",
        json={
            "knowledge_id": "kp_pub",
            "question_type": "multiple_choice",
            "difficulty": 3,
        },
        headers=admin_headers,
    )
    qid = gen.json()["question_id"]

    # draft -> review -> published
    await client.post(
        f"/api/v1/questions/{qid}/status",
        json={"new_status": "review"},
        headers=admin_headers,
    )
    pub = await client.post(
        f"/api/v1/questions/{qid}/status",
        json={"new_status": "published"},
        headers=admin_headers,
    )
    assert pub.status_code == 200
    assert pub.json()["status"] == "published"

    # 学生可以看 published 题目(不含答案)
    resp = await client.get(f"/api/v1/questions/{qid}", headers=auth_headers)
    assert resp.status_code == 200
    assert "answer" not in resp.json() or resp.json().get("answer") is None

    # 教师/管理员可看答案
    staff = await client.get(f"/api/v1/questions/{qid}", headers=admin_headers)
    assert staff.status_code == 200
    assert staff.json().get("answer") is not None


@pytest.mark.asyncio
async def test_review_invalid_transition_returns_400(client, admin_headers):
    gen = await client.post(
        "/api/v1/questions/generate",
        json={
            "knowledge_id": "kp_inv",
            "question_type": "multiple_choice",
            "difficulty": 3,
        },
        headers=admin_headers,
    )
    qid = gen.json()["question_id"]

    # draft -> published 直接迁移,非法
    resp = await client.post(
        f"/api/v1/questions/{qid}/status",
        json={"new_status": "published"},
        headers=admin_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_review_nonexistent_returns_404(client, admin_headers):
    resp = await client.post(
        "/api/v1/questions/99999/status",
        json={"new_status": "review"},
        headers=admin_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_check_answer_published_only(client, admin_headers):
    gen = await client.post(
        "/api/v1/questions/generate",
        json={
            "knowledge_id": "kp_chk",
            "question_type": "multiple_choice",
            "difficulty": 3,
        },
        headers=admin_headers,
    )
    qid = gen.json()["question_id"]

    # draft 状态校验 -> 400
    resp = await client.post(
        f"/api/v1/questions/{qid}/check",
        json={"student_answer": "A"},
        headers=admin_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_check_answer_returns_result(client, admin_headers, auth_headers):
    gen = await client.post(
        "/api/v1/questions/generate",
        json={
            "knowledge_id": "kp_check_ok",
            "question_type": "multiple_choice",
            "difficulty": 3,
        },
        headers=admin_headers,
    )
    qid = gen.json()["question_id"]
    # 走完发布流程
    await client.post(
        f"/api/v1/questions/{qid}/status",
        json={"new_status": "review"},
        headers=admin_headers,
    )
    await client.post(
        f"/api/v1/questions/{qid}/status",
        json={"new_status": "published"},
        headers=admin_headers,
    )

    # 学生答题校验
    resp = await client.post(
        f"/api/v1/questions/{qid}/check",
        json={"student_answer": "A"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "is_correct" in body
    assert "feedback" in body
    assert "reference_answer" in body


@pytest.mark.asyncio
async def test_delete_draft_succeeds(client, admin_headers):
    gen = await client.post(
        "/api/v1/questions/generate",
        json={
            "knowledge_id": "kp_del",
            "question_type": "multiple_choice",
            "difficulty": 3,
        },
        headers=admin_headers,
    )
    qid = gen.json()["question_id"]

    resp = await client.post(
        f"/api/v1/questions/{qid}/delete", headers=admin_headers
    )
    assert resp.status_code == 204

    # 确认已删
    get_resp = await client.get(
        f"/api/v1/questions/{qid}", headers=admin_headers
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_published_blocked(client, admin_headers):
    gen = await client.post(
        "/api/v1/questions/generate",
        json={
            "knowledge_id": "kp_del_pub",
            "question_type": "multiple_choice",
            "difficulty": 3,
        },
        headers=admin_headers,
    )
    qid = gen.json()["question_id"]
    await client.post(
        f"/api/v1/questions/{qid}/status",
        json={"new_status": "review"},
        headers=admin_headers,
    )
    await client.post(
        f"/api/v1/questions/{qid}/status",
        json={"new_status": "published"},
        headers=admin_headers,
    )

    resp = await client.post(
        f"/api/v1/questions/{qid}/delete", headers=admin_headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_404(client, admin_headers):
    resp = await client.post(
        "/api/v1/questions/99999/delete", headers=admin_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_generate_with_rag_flag_works(client, admin_headers):
    """use_rag=True 时即使无文档也应成功(降级路径)。"""
    resp = await client.post(
        "/api/v1/questions/generate",
        json={
            "knowledge_id": "kp_rag",
            "question_type": "multiple_choice",
            "difficulty": 3,
            "use_rag": True,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["question_id"] > 0
