"""知识图谱仓储: 节点 + 前置关系持久化。"""

import logging
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.knowledge_graph import KnowledgeGraph, KnowledgeNode
from db.models import KnowledgeNodeORM, KnowledgePrerequisiteORM
from repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class KnowledgeGraphRepository(BaseRepository[KnowledgeNodeORM]):
    """知识图谱仓储。提供批量加载 + 整图重建。"""

    model = KnowledgeNodeORM

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def upsert_node(self, node: KnowledgeNode) -> KnowledgeNodeORM:
        """upsert 知识点节点。"""
        existing = await self.session.execute(
            select(KnowledgeNodeORM).where(KnowledgeNodeORM.public_id == node.id)
        )
        record = existing.scalar_one_or_none()
        if record is None:
            record = KnowledgeNodeORM(
                public_id=node.id,
                name=node.name,
                subject=node.subject,
                difficulty=node.difficulty,
                description=node.description,
                tags=list(node.tags),
            )
            self.session.add(record)
        else:
            record.name = node.name
            record.subject = node.subject
            record.difficulty = node.difficulty
            record.description = node.description
            record.tags = list(node.tags)
            record.version += 1
        await self.session.flush()
        return record

    async def set_prerequisites(
        self, node_db_id: int, prerequisite_db_ids: list[int]
    ) -> None:
        """替换某个节点的所有前置关系。"""
        await self.session.execute(
            delete(KnowledgePrerequisiteORM).where(
                KnowledgePrerequisiteORM.node_id == node_db_id
            )
        )
        for prereq_id in prerequisite_db_ids:
            self.session.add(
                KnowledgePrerequisiteORM(node_id=node_db_id, prerequisite_id=prereq_id)
            )
        await self.session.flush()

    async def load_full_graph(self) -> KnowledgeGraph:
        """从 DB 加载整张知识图谱到内存。"""
        result = await self.session.execute(select(KnowledgeNodeORM))
        nodes_orm = list(result.scalars().all())
        if not nodes_orm:
            logger.warning("Knowledge graph is empty in DB")
            return KnowledgeGraph()

        id_map: dict[str, int] = {n.public_id: n.id for n in nodes_orm}

        prereq_result = await self.session.execute(select(KnowledgePrerequisiteORM))
        prereq_records = list(prereq_result.scalars().all())
        prereq_by_node: dict[int, list[str]] = {}
        for rec in prereq_records:
            prereq_public_id = next(
                (pub for pub, dbid in id_map.items() if dbid == rec.prerequisite_id),
                None,
            )
            if prereq_public_id:
                prereq_by_node.setdefault(rec.node_id, []).append(prereq_public_id)

        graph = KnowledgeGraph()
        for n_orm in nodes_orm:
            node = KnowledgeNode(
                id=n_orm.public_id,
                name=n_orm.name,
                subject=n_orm.subject,
                difficulty=n_orm.difficulty,
                description=n_orm.description,
                prerequisites=prereq_by_node.get(n_orm.id, []),
                tags=list(n_orm.tags or []),
            )
            graph.add_node(node)

        logger.info("Loaded %d knowledge nodes from DB", len(nodes_orm))
        return graph

    async def seed_from_domain_graph(self, graph: KnowledgeGraph) -> int:
        """把内存中的知识图谱写入 DB(初始化用)。返回写入节点数。"""
        db_id_map: dict[str, int] = {}
        count = 0
        for node in graph.nodes.values():
            record = await self.upsert_node(node)
            db_id_map[node.id] = record.id
            count += 1

        for node in graph.nodes.values():
            prereq_db_ids = [db_id_map[pid] for pid in node.prerequisites if pid in db_id_map]
            if prereq_db_ids:
                await self.set_prerequisites(db_id_map[node.id], prereq_db_ids)
        return count
