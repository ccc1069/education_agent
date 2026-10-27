"""题目库测试: LLM 服务 + Repository + QuestionService。"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.models import QuestionORM
from llm import MockLLMProvider, QuestionLLMService, QuestionParseError
from rag import MockEmbeddingProvider
from services import QuestionService


# ---------- QuestionLLMService: 生成 ----------


@pytest.mark.asyncio
async def test_question_llm_service_generates_multiple_choice():
    service = QuestionLLMService(provider=MockLLMProvider())
    payload, meta = await service.generate_question(
        knowledge_id="pythagorean_theorem",
        question_type="multiple_choice",
        difficulty=3,
    )
    assert payload["content"]["stem"]
    assert len(payload["content"]["options"]) == 4
    assert payload["content"]["answer_key"] in {"A", "B", "C", "D"}
    assert payload["answer"] == payload["content"]["answer_key"]
    assert meta["llm_used"] is True
    assert meta["model"]


@pytest.mark.asyncio
async def test_question_llm_service_generates_fill_blank():
    service = QuestionLLMService(provider=MockLLMProvider())
    payload, _ = await service.generate_question(
        knowledge_id="fractions",
        question_type="fill_blank",
        difficulty=2,
    )
    assert "stem" in payload["content"]
    assert payload["answer"]
    assert "___" in payload["content"]["stem"]


@pytest.mark.asyncio
async def test_question_llm_service_generates_true_false():
    service = QuestionLLMService(provider=MockLLMProvider())
    payload, _ = await service.generate_question(
        knowledge_id="integers",
        question_type="true_false",
        difficulty=1,
    )
    assert payload["answer"] in {"true", "false"}


@pytest.mark.asyncio
async def test_question_llm_service_generates_open_ended():
    service = QuestionLLMService(provider=MockLLMProvider())
    payload, _ = await service.generate_question(
        knowledge_id="calculus",
        question_type="open_ended",
        difficulty=5,
    )
    assert payload["content"]["reference_answer"]
    assert payload["answer"] == payload["content"]["reference_answer"]


@pytest.mark.asyncio
async def test_question_llm_service_parses_markdown_fenced_json():
    """LLM 返回带 ```json 包裹的 JSON,服务应能解析。"""
    raw_json = json.dumps(
        {
            "stem": "1+1=?",
            "options": [
                {"key": "A", "text": "1"},
                {"key": "B", "text": "2"},
            ],
            "answer_key": "B",
            "analysis": "1+1=2",
        },
        ensure_ascii=False,
    )
    fake_response = MagicMock()
    fake_response.content = f"```json\n{raw_json}\n```"
    fake_response.model = "fake"
    fake_response.total_tokens = 50
    fake_response.latency_ms = 10.0

    mock_provider = MockLLMProvider()
    mock_provider.complete = AsyncMock(return_value=fake_response)

    service = QuestionLLMService(provider=mock_provider)
    payload, _ = await service.generate_question("test", "multiple_choice", 1)
    assert payload["answer"] == "B"
    assert payload["content"]["options"][1]["text"] == "2"


@pytest.mark.asyncio
async def test_question_llm_service_falls_back_to_template_on_parse_error():
    fake_response = MagicMock()
    fake_response.content = "not a json at all"
    fake_response.model = "fake"
    fake_response.total_tokens = 5
    fake_response.latency_ms = 10.0

    mock_provider = MockLLMProvider()
    mock_provider.complete = AsyncMock(return_value=fake_response)

    service = QuestionLLMService(provider=mock_provider)
    payload, meta = await service.generate_question("kp1", "multiple_choice", 3)
    assert meta["llm_used"] is True
    assert meta["fallback"] == "template"
    assert payload["content"]["stem"]
    assert payload["answer"] == "A"


@pytest.mark.asyncio
async def test_question_llm_service_rejects_invalid_question_type():
    service = QuestionLLMService(provider=MockLLMProvider())
    # Mock provider 不识别未知题型,会返回选择题 JSON,服务校验时拒绝
    fake_response = MagicMock()
    fake_response.content = json.dumps({"stem": "x", "answer": "y"})
    fake_response.model = "fake"
    fake_response.total_tokens = 5
    fake_response.latency_ms = 1.0

    mock_provider = MockLLMProvider()
    mock_provider.complete = AsyncMock(return_value=fake_response)

    service = QuestionLLMService(provider=mock_provider)
    payload, meta = await service.generate_question("kp", "unknown_type", 3)
    # 未知题型应触发 QuestionParseError -> fallback template
    assert meta["fallback"] == "template"


# ---------- QuestionLLMService: 校验 ----------


@pytest.mark.asyncio
async def test_question_llm_service_verify_correct_answer():
    service = QuestionLLMService(provider=MockLLMProvider())
    is_correct, feedback, meta = await service.verify_answer(
        question_stem="1+1=?",
        reference_answer="2",
        student_answer="2",
    )
    assert is_correct is True
    assert meta["llm_used"] is True
    assert feedback


@pytest.mark.asyncio
async def test_question_llm_service_verify_wrong_answer():
    service = QuestionLLMService(provider=MockLLMProvider())
    is_correct, _, _ = await service.verify_answer(
        question_stem="1+1=?",
        reference_answer="2",
        student_answer="3",
    )
    assert is_correct is False


@pytest.mark.asyncio
async def test_question_llm_service_verify_falls_back_on_parse_error():
    fake_response = MagicMock()
    fake_response.content = "garbage"
    fake_response.model = "fake"
    fake_response.total_tokens = 5
    fake_response.latency_ms = 1.0

    mock_provider = MockLLMProvider()
    mock_provider.complete = AsyncMock(return_value=fake_response)

    service = QuestionLLMService(provider=mock_provider)
    is_correct, _, meta = await service.verify_answer("q", "ref", "stu")
    assert meta["llm_used"] is False
    assert meta["fallback"] == "exact_match"
    # 严格匹配: ref != stu
    assert is_correct is False


# ---------- QuestionService: 生成 + 去重 ----------


@pytest.fixture
def mock_embedding():
    return MockEmbeddingProvider()


@pytest.fixture
def mock_llm():
    return MockLLMProvider()


@pytest.mark.asyncio
async def test_question_service_generate_creates_draft_question(
    db_session, mock_embedding, mock_llm
):
    service = QuestionService(
        db_session,
        llm_service=QuestionLLMService(provider=mock_llm),
        embedding_provider=mock_embedding,
    )
    result = await service.generate_question(
        knowledge_id="pythagorean",
        question_type="multiple_choice",
        difficulty=3,
        created_by=1,
    )
    assert result["is_duplicate"] is False
    assert result["question_id"] > 0
    assert result["status"] == "draft"

    detail = await service.get_question(result["question_id"])
    assert detail["knowledge_id"] == "pythagorean"
    assert detail["question_type"] == "multiple_choice"
    assert detail["difficulty"] == 3
    assert detail["created_by"] == 1


@pytest.mark.asyncio
async def test_question_service_generate_deduplicates(
    db_session, mock_embedding, mock_llm
):
    """相同知识点 + 题型 + 难度 -> Mock 返回相同 JSON -> embedding 相同 -> 视为重复。"""
    service = QuestionService(
        db_session,
        llm_service=QuestionLLMService(provider=mock_llm),
        embedding_provider=mock_embedding,
    )
    r1 = await service.generate_question(
        knowledge_id="kp1", question_type="multiple_choice", difficulty=3
    )
    r2 = await service.generate_question(
        knowledge_id="kp1", question_type="multiple_choice", difficulty=3
    )
    assert r1["is_duplicate"] is False
    # Mock 返回的 JSON 完全相同 -> embedding 相同 -> 相似度=1.0 >= 0.92
    assert r2["is_duplicate"] is True
    assert r2["question_id"] == r1["question_id"]


@pytest.mark.asyncio
async def test_question_service_generate_rejects_invalid_type(
    db_session, mock_embedding, mock_llm
):
    service = QuestionService(
        db_session,
        llm_service=QuestionLLMService(provider=mock_llm),
        embedding_provider=mock_embedding,
    )
    with pytest.raises(ValueError, match="unsupported question_type"):
        await service.generate_question(
            knowledge_id="kp", question_type="invalid", difficulty=3
        )


@pytest.mark.asyncio
async def test_question_service_generate_rejects_invalid_difficulty(
    db_session, mock_embedding, mock_llm
):
    service = QuestionService(
        db_session,
        llm_service=QuestionLLMService(provider=mock_llm),
        embedding_provider=mock_embedding,
    )
    with pytest.raises(ValueError, match="difficulty"):
        await service.generate_question(
            knowledge_id="kp", question_type="multiple_choice", difficulty=0
        )


@pytest.mark.asyncio
async def test_question_service_generate_rejects_empty_knowledge_id(
    db_session, mock_embedding, mock_llm
):
    service = QuestionService(
        db_session,
        llm_service=QuestionLLMService(provider=mock_llm),
        embedding_provider=mock_embedding,
    )
    with pytest.raises(ValueError, match="knowledge_id"):
        await service.generate_question(
            knowledge_id="", question_type="multiple_choice", difficulty=3
        )


# ---------- QuestionService: 列表 + 详情 ----------


@pytest.mark.asyncio
async def test_question_service_list_filters_by_status(
    db_session, mock_embedding, mock_llm
):
    service = QuestionService(
        db_session,
        llm_service=QuestionLLMService(provider=mock_llm),
        embedding_provider=mock_embedding,
    )
    await service.generate_question(
        knowledge_id="kp1", question_type="multiple_choice", difficulty=3
    )
    await service.generate_question(
        knowledge_id="kp2", question_type="fill_blank", difficulty=2
    )

    drafts = await service.list_questions(status="draft")
    assert len(drafts) == 2
    assert all(q["status"] == "draft" for q in drafts)


@pytest.mark.asyncio
async def test_question_service_list_filters_by_knowledge_id(
    db_session, mock_embedding, mock_llm
):
    service = QuestionService(
        db_session,
        llm_service=QuestionLLMService(provider=mock_llm),
        embedding_provider=mock_embedding,
    )
    await service.generate_question(
        knowledge_id="kp_a", question_type="multiple_choice", difficulty=3
    )
    # 第二次会因为 mock 输出相同被去重,改个题型避免
    await service.generate_question(
        knowledge_id="kp_b", question_type="fill_blank", difficulty=2
    )

    docs = await service.list_questions(knowledge_id="kp_a")
    assert len(docs) == 1
    assert docs[0]["knowledge_id"] == "kp_a"


@pytest.mark.asyncio
async def test_question_service_get_nonexistent_returns_none(db_session, mock_embedding, mock_llm):
    service = QuestionService(
        db_session,
        llm_service=QuestionLLMService(provider=mock_llm),
        embedding_provider=mock_embedding,
    )
    assert await service.get_question(99999) is None


@pytest.mark.asyncio
async def test_question_service_get_excludes_answer_by_default(
    db_session, mock_embedding, mock_llm
):
    service = QuestionService(
        db_session,
        llm_service=QuestionLLMService(provider=mock_llm),
        embedding_provider=mock_embedding,
    )
    r = await service.generate_question(
        knowledge_id="kp", question_type="multiple_choice", difficulty=3
    )
    summary = await service.get_question(r["question_id"])
    assert "answer" not in summary
    assert "analysis" not in summary


# ---------- QuestionService: 状态机 ----------


@pytest.mark.asyncio
async def test_question_service_review_transitions_draft_to_review(
    db_session, mock_embedding, mock_llm
):
    service = QuestionService(
        db_session,
        llm_service=QuestionLLMService(provider=mock_llm),
        embedding_provider=mock_embedding,
    )
    r = await service.generate_question(
        knowledge_id="kp", question_type="multiple_choice", difficulty=3
    )
    reviewed = await service.review_question(r["question_id"], "review")
    assert reviewed["status"] == "review"


@pytest.mark.asyncio
async def test_question_service_review_transitions_review_to_published(
    db_session, mock_embedding, mock_llm
):
    service = QuestionService(
        db_session,
        llm_service=QuestionLLMService(provider=mock_llm),
        embedding_provider=mock_embedding,
    )
    r = await service.generate_question(
        knowledge_id="kp", question_type="multiple_choice", difficulty=3
    )
    await service.review_question(r["question_id"], "review")
    published = await service.review_question(r["question_id"], "published")
    assert published["status"] == "published"


@pytest.mark.asyncio
async def test_question_service_review_rejects_invalid_transition(
    db_session, mock_embedding, mock_llm
):
    """draft -> published 是非法直接迁移。"""
    service = QuestionService(
        db_session,
        llm_service=QuestionLLMService(provider=mock_llm),
        embedding_provider=mock_embedding,
    )
    r = await service.generate_question(
        knowledge_id="kp", question_type="multiple_choice", difficulty=3
    )
    with pytest.raises(ValueError, match="invalid transition"):
        await service.review_question(r["question_id"], "published")


@pytest.mark.asyncio
async def test_question_service_review_nonexistent_returns_none(
    db_session, mock_embedding, mock_llm
):
    service = QuestionService(
        db_session,
        llm_service=QuestionLLMService(provider=mock_llm),
        embedding_provider=mock_embedding,
    )
    assert await service.review_question(99999, "review") is None


# ---------- QuestionService: 答案校验 ----------


@pytest.mark.asyncio
async def test_question_service_verify_answer_published_only(
    db_session, mock_embedding, mock_llm
):
    """未发布的题目不允许校验答案。"""
    service = QuestionService(
        db_session,
        llm_service=QuestionLLMService(provider=mock_llm),
        embedding_provider=mock_embedding,
    )
    r = await service.generate_question(
        knowledge_id="kp", question_type="multiple_choice", difficulty=3
    )
    # draft 状态
    with pytest.raises(ValueError, match="not published"):
        await service.verify_answer(r["question_id"], "A")


@pytest.mark.asyncio
async def test_question_service_verify_answer_returns_correct(
    db_session, mock_embedding, mock_llm
):
    service = QuestionService(
        db_session,
        llm_service=QuestionLLMService(provider=mock_llm),
        embedding_provider=mock_embedding,
    )
    r = await service.generate_question(
        knowledge_id="kp", question_type="multiple_choice", difficulty=3
    )
    await service.review_question(r["question_id"], "review")
    await service.review_question(r["question_id"], "published")

    # Mock answer_key 是 A,题目 stem 含 "Mock 选择题",校验也走 Mock
    # Mock verify 用 "参考答案" 字段匹配,reference_answer 是 "A",student_answer="A" -> correct
    result = await service.verify_answer(r["question_id"], "A")
    assert result["is_correct"] is True
    assert result["reference_answer"] == "A"


@pytest.mark.asyncio
async def test_question_service_verify_nonexistent_returns_none(
    db_session, mock_embedding, mock_llm
):
    service = QuestionService(
        db_session,
        llm_service=QuestionLLMService(provider=mock_llm),
        embedding_provider=mock_embedding,
    )
    assert await service.verify_answer(99999, "A") is None


# ---------- QuestionService: 删除 ----------


@pytest.mark.asyncio
async def test_question_service_delete_draft_succeeds(
    db_session, mock_embedding, mock_llm
):
    service = QuestionService(
        db_session,
        llm_service=QuestionLLMService(provider=mock_llm),
        embedding_provider=mock_embedding,
    )
    r = await service.generate_question(
        knowledge_id="kp", question_type="multiple_choice", difficulty=3
    )
    deleted = await service.delete_question(r["question_id"])
    assert deleted is True
    assert await service.get_question(r["question_id"]) is None


@pytest.mark.asyncio
async def test_question_service_delete_published_blocked(
    db_session, mock_embedding, mock_llm
):
    """published 题目不允许直接删除(需先 archive)。"""
    service = QuestionService(
        db_session,
        llm_service=QuestionLLMService(provider=mock_llm),
        embedding_provider=mock_embedding,
    )
    r = await service.generate_question(
        knowledge_id="kp", question_type="multiple_choice", difficulty=3
    )
    await service.review_question(r["question_id"], "review")
    await service.review_question(r["question_id"], "published")
    with pytest.raises(ValueError, match="cannot delete"):
        await service.delete_question(r["question_id"])


@pytest.mark.asyncio
async def test_question_service_delete_nonexistent_returns_false(
    db_session, mock_embedding, mock_llm
):
    service = QuestionService(
        db_session,
        llm_service=QuestionLLMService(provider=mock_llm),
        embedding_provider=mock_embedding,
    )
    assert await service.delete_question(99999) is False


# ---------- QuestionService: RAG 集成 ----------


@pytest.mark.asyncio
async def test_question_service_generate_with_rag_does_not_crash(
    db_session, mock_embedding, mock_llm
):
    """注入 RAG service 时,即使检索失败也应降级继续生成。"""
    service = QuestionService(
        db_session,
        llm_service=QuestionLLMService(provider=mock_llm),
        embedding_provider=mock_embedding,
    )

    # Mock RAG service: 检索返回空
    mock_rag = MagicMock()
    mock_rag.search = AsyncMock(return_value=[])

    result = await service.generate_question(
        knowledge_id="kp",
        question_type="multiple_choice",
        difficulty=3,
        rag_service=mock_rag,
    )
    assert result["is_duplicate"] is False
    assert result["question_id"] > 0
