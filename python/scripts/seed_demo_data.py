"""全流程演示种子: 执行 SQL + 补 RAG embedding + 审计 HMAC 链。

用法:
    cd python
    python -m scripts.seed_demo_data

依赖:
    - 已 alembic upgrade head
    - DATABASE_URL 指向目标库(默认读 ../.env / settings)

演示账号(密码均为 demo123456):
    student@demo.com / teacher@demo.com / admin@demo.com

班级邀请码:
    DEMOCLS01 初二(1)班 · 数学强化(教师)
    DEMOGEO02 初二几何专题班(教师)
    DEMOADM03 教务演示班(管理员)
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text  # noqa: E402

from config.settings import settings  # noqa: E402
from db.base import AsyncSessionLocal, init_db  # noqa: E402
from db.models import AuditLogORM, DocumentChunkORM, DocumentORM  # noqa: E402
from rag.embedding import MockEmbeddingProvider, get_embedding_provider  # noqa: E402
from services.audit_service import AuditService  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SQL_PATH = Path(__file__).with_name("seed_demo_data.sql")

CHUNK_SEEDS = (
    (
        "初中数学 · 方程专题讲义",
        [
            (
                0,
                "一元一次方程的一般形式是 ax+b=0(a≠0)。移项时变号,两边同除以 a 得 x=-b/a。"
                "检验:将解代回原方程验证左右相等。",
            ),
            (
                1,
                "二元一次方程组可用代入法或加减法。目标是消去一个未知数,得到一元方程后再回代。"
                "几何意义是两条直线的交点。",
            ),
        ],
    ),
    (
        "二次函数图像速查",
        [
            (
                0,
                "二次函数 y=ax²+bx+c(a≠0)。a>0 开口向上,a<0 开口向下。"
                "对称轴 x=-b/(2a),顶点坐标可据此求出。",
            ),
        ],
    ),
    (
        "概率入门笔记",
        [
            (
                0,
                "古典概型:基本事件等可能时,事件概率=有利结果数/总结果数。"
                "对立事件概率之和为 1;互斥事件可直接相加。",
            ),
        ],
    ),
)


def _split_sql_statements(raw: str) -> list[str]:
    """按分号切分(本种子文件字符串内不含分号)。跳过空语句与纯注释。"""
    cleaned = re.sub(r"--.*?$", "", raw, flags=re.MULTILINE)
    parts: list[str] = []
    for chunk in cleaned.split(";"):
        stmt = chunk.strip()
        if not stmt:
            continue
        upper = stmt.upper()
        if upper in {"BEGIN", "COMMIT", "ROLLBACK"}:
            continue
        parts.append(stmt)
    return parts


def _escape_sqlalchemy_binds(stmt: str) -> str:
    """避免 JSON 中的 :0 / :demo 被 SQLAlchemy 当成 bind 参数;保留 PG 的 ::cast。"""
    protected = stmt.replace("::", "\x00PGCAST\x00")
    escaped = protected.replace(":", "\\:")
    return escaped.replace("\x00PGCAST\x00", "::")


async def _run_sql(session) -> None:
    raw = SQL_PATH.read_text(encoding="utf-8")
    stmts = _split_sql_statements(raw)
    for i, stmt in enumerate(stmts, 1):
        try:
            await session.execute(text(_escape_sqlalchemy_binds(stmt)))
        except Exception:
            logger.exception("SQL 第 %d 条执行失败:\n%s", i, stmt[:400])
            raise
    await session.commit()
    logger.info("已执行 SQL 种子: %s (%d 条语句)", SQL_PATH.name, len(stmts))


def _is_seed_doc(doc: DocumentORM) -> bool:
    meta = doc.metadata_ or {}
    return meta.get("seed") == "demo"


async def _seed_document_chunks(session) -> None:
    """写入/校正种子分块 embedding,维度与当前 EmbeddingProvider 对齐。"""
    embedder = get_embedding_provider()
    if isinstance(embedder, MockEmbeddingProvider):
        logger.warning(
            "种子使用 MockEmbeddingProvider(dim=%d);生产检索请配置真实 EMBEDDING_*",
            embedder.dimension,
        )
    else:
        logger.info(
            "种子使用 %s (configured_dim=%d) 生成向量",
            embedder.name,
            embedder.dimension,
        )

    # 先探测真实维度(配置 dim 可能与 API 返回不一致)
    probe = await embedder.embed("embedding dimension probe")
    expected_dim = len(probe)
    logger.info("Embedding 实际维度: %d", expected_dim)

    for title, chunks in CHUNK_SEEDS:
        result = await session.execute(select(DocumentORM).where(DocumentORM.title == title))
        docs = list(result.scalars().all())
        doc = next((d for d in docs if _is_seed_doc(d)), None)
        if doc is None:
            logger.warning("文档不存在,跳过分块: %s", title)
            continue
        for idx, content in chunks:
            existing = await session.execute(
                select(DocumentChunkORM).where(
                    DocumentChunkORM.document_id == doc.id,
                    DocumentChunkORM.chunk_index == idx,
                )
            )
            row = existing.scalar_one_or_none()
            emb = row.embedding if row is not None else None
            need_embed = row is None or not emb or len(emb) != expected_dim
            if not need_embed:
                continue
            vector = await embedder.embed(content)
            if row is None:
                session.add(
                    DocumentChunkORM(
                        document_id=doc.id,
                        chunk_index=idx,
                        content=content,
                        embedding=vector,
                        token_count=max(1, len(content) // 2),
                        tenant_id=doc.tenant_id,
                        metadata_={"seed": "demo"},
                    )
                )
                logger.info("已写入分块: doc=%s chunk=%d dim=%d", title, idx, len(vector))
            else:
                row.content = content
                row.embedding = vector
                row.token_count = max(1, len(content) // 2)
                logger.info(
                    "已校正分块 embedding: doc=%s chunk=%d dim=%d",
                    title,
                    idx,
                    len(vector),
                )
        doc.total_chunks = len(chunks)
        doc.status = "indexed"
        doc.error_message = None
    await session.commit()


async def _seed_audit_logs(session) -> None:
    """审计链依赖运行时 HMAC secret,必须用 AuditService 写入。"""
    result = await session.execute(select(AuditLogORM).limit(50))
    logs = list(result.scalars().all())
    if any((log.metadata_ or {}).get("seed") == "demo" for log in logs):
        logger.info("审计演示日志已存在,跳过")
        return

    svc = AuditService(session)
    entries = [
        ("admin@demo.com", "auth.login", "user:admin@demo.com", {"seed": "demo"}),
        ("teacher@demo.com", "class.create", "class:DEMOCLS01", {"seed": "demo"}),
        ("teacher@demo.com", "assignment.publish", "assignment:week1", {"seed": "demo"}),
        ("student@demo.com", "auth.login", "user:student@demo.com", {"seed": "demo"}),
        ("student@demo.com", "practice.submit", "knowledge:fractions", {"seed": "demo"}),
    ]
    for actor, action, target, meta in entries:
        # AuditService.log_action 内部会 commit
        await svc.log_action(actor=actor, action=action, target=target, metadata=meta)
    logger.info("已写入 %d 条审计演示日志(HMAC 链)", len(entries))


async def main() -> None:
    if not SQL_PATH.exists():
        logger.error("找不到 SQL 文件: %s", SQL_PATH)
        sys.exit(1)

    logger.info("目标库: %s", settings.database_url)
    await init_db()
    async with AsyncSessionLocal() as session:
        await _run_sql(session)
        await _seed_document_chunks(session)
        await _seed_audit_logs(session)

    logger.info(
        "全流程种子完成。登录: student@demo.com / teacher@demo.com / admin@demo.com , 密码 demo123456"
    )


if __name__ == "__main__":
    asyncio.run(main())
