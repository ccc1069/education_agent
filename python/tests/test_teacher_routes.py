"""教师后台 API 集成测试: 班级 + 作业 + 看板。"""

import pytest


# ---------- 权限: 未认证 ----------


@pytest.mark.asyncio
async def test_create_class_requires_auth(client):
    resp = await client.post(
        "/api/v1/teacher/classes",
        json={"name": "Math 101", "description": ""},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_classes_requires_auth(client):
    resp = await client.get("/api/v1/teacher/classes")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_assignment_requires_auth(client):
    resp = await client.post(
        "/api/v1/teacher/assignments",
        json={
            "title": "HW1",
            "class_id": 1,
            "question_ids": [1],
        },
    )
    assert resp.status_code == 401


# ---------- 权限: 学生不能管理班级/作业 ----------


@pytest.mark.asyncio
async def test_student_cannot_create_class(client, auth_headers):
    resp = await client.post(
        "/api/v1/teacher/classes",
        json={"name": "Sneaky", "description": ""},
        headers=auth_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_student_cannot_list_classes(client, auth_headers):
    resp = await client.get("/api/v1/teacher/classes", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_student_cannot_create_assignment(client, auth_headers):
    resp = await client.post(
        "/api/v1/teacher/assignments",
        json={
            "title": "HW",
            "class_id": 1,
            "question_ids": [1],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 403


# ---------- 班级 CRUD (教师视角) ----------


@pytest.mark.asyncio
async def test_teacher_creates_class_successfully(client, teacher_headers):
    resp = await client.post(
        "/api/v1/teacher/classes",
        json={"name": "Math 101", "description": "Algebra basics"},
        headers=teacher_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] > 0
    assert body["name"] == "Math 101"
    assert body["description"] == "Algebra basics"
    assert len(body["invite_code"]) == 8
    assert body["is_active"] is True
    assert body["member_count"] == 0


@pytest.mark.asyncio
async def test_teacher_creates_class_rejects_empty_name(client, teacher_headers):
    resp = await client.post(
        "/api/v1/teacher/classes",
        json={"name": "", "description": ""},
        headers=teacher_headers,
    )
    assert resp.status_code == 422  # Pydantic validation


@pytest.mark.asyncio
async def test_teacher_lists_their_classes(client, teacher_headers):
    # 创建 2 个班级
    await client.post(
        "/api/v1/teacher/classes",
        json={"name": "A"},
        headers=teacher_headers,
    )
    await client.post(
        "/api/v1/teacher/classes",
        json={"name": "B"},
        headers=teacher_headers,
    )
    resp = await client.get("/api/v1/teacher/classes", headers=teacher_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    names = {c["name"] for c in body}
    assert names == {"A", "B"}


@pytest.mark.asyncio
async def test_admin_lists_all_classes_and_assignments(
    client, teacher_headers, admin_headers
):
    """管理员可看到教师创建的班级与作业,不仅限于自己名下。"""
    cls_id, q_id = await _setup_class_with_published_question(client, teacher_headers)
    # 把班级改个可识别名字(通过再创建一个)
    create = await client.post(
        "/api/v1/teacher/classes",
        json={"name": "Teacher Owned Class", "description": "for admin view"},
        headers=teacher_headers,
    )
    assert create.status_code == 201
    owned_id = create.json()["id"]

    asg = await client.post(
        "/api/v1/teacher/assignments",
        json={
            "title": "Admin Visible HW",
            "class_id": cls_id,
            "question_ids": [q_id],
        },
        headers=teacher_headers,
    )
    assert asg.status_code == 201, asg.text

    classes = await client.get("/api/v1/teacher/classes", headers=admin_headers)
    assert classes.status_code == 200
    names = {c["name"] for c in classes.json()}
    assert "Teacher Owned Class" in names
    assert any(c["id"] == owned_id for c in classes.json())

    assignments = await client.get("/api/v1/teacher/assignments", headers=admin_headers)
    assert assignments.status_code == 200
    titles = {a["title"] for a in assignments.json()}
    assert "Admin Visible HW" in titles


@pytest.mark.asyncio
async def test_get_class_detail_returns_members(client, teacher_headers):
    create = await client.post(
        "/api/v1/teacher/classes",
        json={"name": "C"},
        headers=teacher_headers,
    )
    cls_id = create.json()["id"]

    resp = await client.get(
        f"/api/v1/teacher/classes/{cls_id}",
        headers=teacher_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == cls_id
    assert body["members"] == []


@pytest.mark.asyncio
async def test_get_nonexistent_class_returns_404(client, teacher_headers):
    resp = await client.get(
        "/api/v1/teacher/classes/99999",
        headers=teacher_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_archive_class(client, teacher_headers):
    create = await client.post(
        "/api/v1/teacher/classes",
        json={"name": "C"},
        headers=teacher_headers,
    )
    cls_id = create.json()["id"]

    resp = await client.post(
        f"/api/v1/teacher/classes/{cls_id}/archive",
        headers=teacher_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


# ---------- 学生加入班级 ----------


@pytest.mark.asyncio
async def test_student_joins_class_via_invite_code(client, teacher_headers, auth_headers):
    # 教师创建班级
    create = await client.post(
        "/api/v1/teacher/classes",
        json={"name": "Joinable"},
        headers=teacher_headers,
    )
    invite_code = create.json()["invite_code"]

    # 学生加入
    resp = await client.post(
        "/api/v1/teacher/classes/join",
        json={"invite_code": invite_code},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["already_member"] is False


@pytest.mark.asyncio
async def test_student_join_invalid_code_returns_400(client, auth_headers):
    resp = await client.post(
        "/api/v1/teacher/classes/join",
        json={"invite_code": "BADCODE1"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_teacher_cannot_join_class(client, teacher_headers):
    """教师角色不能调用 /join 接口。"""
    resp = await client.post(
        "/api/v1/teacher/classes/join",
        json={"invite_code": "ANYCODE1"},
        headers=teacher_headers,
    )
    assert resp.status_code == 403


# ---------- 成员管理 ----------


@pytest.mark.asyncio
async def test_list_class_members_after_join(client, teacher_headers, auth_headers):
    create = await client.post(
        "/api/v1/teacher/classes",
        json={"name": "C"},
        headers=teacher_headers,
    )
    cls_id = create.json()["id"]
    invite = create.json()["invite_code"]

    await client.post(
        "/api/v1/teacher/classes/join",
        json={"invite_code": invite},
        headers=auth_headers,
    )

    resp = await client.get(
        f"/api/v1/teacher/classes/{cls_id}/members",
        headers=teacher_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["public_id"] == "student-test-pubid"


@pytest.mark.asyncio
async def test_remove_member(client, teacher_headers, auth_headers):
    create = await client.post(
        "/api/v1/teacher/classes",
        json={"name": "C"},
        headers=teacher_headers,
    )
    cls_id = create.json()["id"]
    invite = create.json()["invite_code"]

    join = await client.post(
        "/api/v1/teacher/classes/join",
        json={"invite_code": invite},
        headers=auth_headers,
    )
    learner_id = join.json()["class_id"]  # 不是 learner_id,得通过 members 接口拿

    members = await client.get(
        f"/api/v1/teacher/classes/{cls_id}/members",
        headers=teacher_headers,
    )
    actual_learner_id = members.json()[0]["learner_id"]

    resp = await client.post(
        f"/api/v1/teacher/classes/{cls_id}/members/{actual_learner_id}/delete",
        headers=teacher_headers,
    )
    assert resp.status_code == 204

    # 再查成员,应为空
    members_after = await client.get(
        f"/api/v1/teacher/classes/{cls_id}/members",
        headers=teacher_headers,
    )
    assert members_after.json() == []


# ---------- 作业 CRUD ----------


async def _setup_class_with_published_question(client, headers):
    """辅助: 教师创建班级 + 直接在 DB 插入 published 题目,返回 (class_id, question_id)。"""
    create = await client.post(
        "/api/v1/teacher/classes",
        json={"name": "C"},
        headers=headers,
    )
    cls_id = create.json()["id"]

    # 通过 /questions/generate 生成一道题(默认 draft),走 draft -> review -> published
    gen = await client.post(
        "/api/v1/questions/generate",
        json={
            "knowledge_id": "pythagorean",
            "question_type": "multiple_choice",
            "difficulty": 3,
        },
        headers=headers,
    )
    q_id = gen.json()["question_id"]
    await client.post(
        f"/api/v1/questions/{q_id}/status",
        json={"new_status": "review"},
        headers=headers,
    )
    await client.post(
        f"/api/v1/questions/{q_id}/status",
        json={"new_status": "published"},
        headers=headers,
    )
    return cls_id, q_id


@pytest.mark.asyncio
async def test_teacher_creates_assignment(client, teacher_headers):
    cls_id, q_id = await _setup_class_with_published_question(client, teacher_headers)

    resp = await client.post(
        "/api/v1/teacher/assignments",
        json={
            "title": "HW1",
            "class_id": cls_id,
            "question_ids": [q_id],
            "description": "Practice",
        },
        headers=teacher_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "draft"
    assert body["question_ids"] == [q_id]
    assert body["title"] == "HW1"


@pytest.mark.asyncio
async def test_create_assignment_rejects_unpublished_question(client, teacher_headers):
    """题目未发布时不能布置。"""
    create = await client.post(
        "/api/v1/teacher/classes",
        json={"name": "C"},
        headers=teacher_headers,
    )
    cls_id = create.json()["id"]

    # 生成题目但不发布
    gen = await client.post(
        "/api/v1/questions/generate",
        json={
            "knowledge_id": "kp",
            "question_type": "multiple_choice",
            "difficulty": 3,
        },
        headers=teacher_headers,
    )
    q_id = gen.json()["question_id"]

    resp = await client.post(
        "/api/v1/teacher/assignments",
        json={
            "title": "HW",
            "class_id": cls_id,
            "question_ids": [q_id],
        },
        headers=teacher_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_assignment_state_machine_via_api(client, teacher_headers):
    cls_id, q_id = await _setup_class_with_published_question(client, teacher_headers)
    create = await client.post(
        "/api/v1/teacher/assignments",
        json={
            "title": "HW",
            "class_id": cls_id,
            "question_ids": [q_id],
        },
        headers=teacher_headers,
    )
    a_id = create.json()["id"]

    # draft -> published
    resp = await client.post(
        f"/api/v1/teacher/assignments/{a_id}/status",
        json={"new_status": "published"},
        headers=teacher_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"

    # published -> closed
    resp = await client.post(
        f"/api/v1/teacher/assignments/{a_id}/status",
        json={"new_status": "closed"},
        headers=teacher_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"


@pytest.mark.asyncio
async def test_invalid_assignment_transition_returns_400(client, teacher_headers):
    cls_id, q_id = await _setup_class_with_published_question(client, teacher_headers)
    create = await client.post(
        "/api/v1/teacher/assignments",
        json={
            "title": "HW",
            "class_id": cls_id,
            "question_ids": [q_id],
        },
        headers=teacher_headers,
    )
    a_id = create.json()["id"]

    # draft -> closed 非法
    resp = await client.post(
        f"/api/v1/teacher/assignments/{a_id}/status",
        json={"new_status": "closed"},
        headers=teacher_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_draft_assignment(client, teacher_headers):
    cls_id, q_id = await _setup_class_with_published_question(client, teacher_headers)
    create = await client.post(
        "/api/v1/teacher/assignments",
        json={
            "title": "HW",
            "class_id": cls_id,
            "question_ids": [q_id],
        },
        headers=teacher_headers,
    )
    a_id = create.json()["id"]

    resp = await client.post(
        f"/api/v1/teacher/assignments/{a_id}/delete",
        headers=teacher_headers,
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_published_assignment_returns_400(client, teacher_headers):
    cls_id, q_id = await _setup_class_with_published_question(client, teacher_headers)
    create = await client.post(
        "/api/v1/teacher/assignments",
        json={
            "title": "HW",
            "class_id": cls_id,
            "question_ids": [q_id],
        },
        headers=teacher_headers,
    )
    a_id = create.json()["id"]
    await client.post(
        f"/api/v1/teacher/assignments/{a_id}/status",
        json={"new_status": "published"},
        headers=teacher_headers,
    )

    resp = await client.post(
        f"/api/v1/teacher/assignments/{a_id}/delete",
        headers=teacher_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_assignments_by_class(client, teacher_headers):
    cls_id, q_id = await _setup_class_with_published_question(client, teacher_headers)
    for i in range(3):
        await client.post(
            "/api/v1/teacher/assignments",
            json={
                "title": f"HW{i}",
                "class_id": cls_id,
                "question_ids": [q_id],
            },
            headers=teacher_headers,
        )

    resp = await client.get(
        f"/api/v1/teacher/assignments?class_id={cls_id}",
        headers=teacher_headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 3


# ---------- 学情看板 ----------


@pytest.mark.asyncio
async def test_dashboard_for_empty_class(client, teacher_headers):
    create = await client.post(
        "/api/v1/teacher/classes",
        json={"name": "C"},
        headers=teacher_headers,
    )
    cls_id = create.json()["id"]

    resp = await client.get(
        f"/api/v1/teacher/classes/{cls_id}/dashboard",
        headers=teacher_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["member_count"] == 0
    assert body["avg_mastery"] == 0.0


@pytest.mark.asyncio
async def test_dashboard_returns_404_for_nonexistent(client, teacher_headers):
    resp = await client.get(
        "/api/v1/teacher/classes/99999/dashboard",
        headers=teacher_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_dashboard_requires_teacher_role(client, auth_headers):
    """学生不能访问班级看板。"""
    resp = await client.get(
        "/api/v1/teacher/classes/1/dashboard",
        headers=auth_headers,
    )
    assert resp.status_code == 403


# ---------- 跨教师隔离 ----------


@pytest.mark.asyncio
async def test_teacher_a_cannot_see_teacher_b_class(client, teacher_headers, auth_headers):
    """教师 A 创建的班级,学生不能访问看板(权限隔离)。"""
    create = await client.post(
        "/api/v1/teacher/classes",
        json={"name": "Owner only"},
        headers=teacher_headers,
    )
    cls_id = create.json()["id"]

    # 学生直接访问看板 -> 403
    resp = await client.get(
        f"/api/v1/teacher/classes/{cls_id}/dashboard",
        headers=auth_headers,
    )
    assert resp.status_code == 403
