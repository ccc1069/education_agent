"""事件仓储: 事件溯源存储 + 历史查询。"""

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.event_bus import Event, EventType
from db.models import EventORM
from repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class EventRepository(BaseRepository[EventORM]):
    """事件溯源仓储。所有事件先入 DB,再分发到订阅者。"""

    model = EventORM

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def append(self, event: Event) -> EventORM:
        """追加事件到事件流(append-only)。"""
        record = EventORM(
            public_id=event.id,
            type=event.type.value,
            source=event.source,
            learner_public_id=event.learner_id,
            data=event.data,
            correlation_id=event.correlation_id,
            timestamp=event.timestamp,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def list_by_learner(
        self,
        learner_public_id: str,
        event_type: EventType | None = None,
        limit: int = 50,
    ) -> list[EventORM]:
        """按学习者查询事件历史(倒序)。"""
        stmt = select(EventORM).where(EventORM.learner_public_id == learner_public_id)
        if event_type:
            stmt = stmt.where(EventORM.type == event_type.value)
        stmt = stmt.order_by(EventORM.timestamp.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_correlation(self, correlation_id: str) -> list[EventORM]:
        """按 correlation_id 查询事件链(分布式追踪)。"""
        result = await self.session.execute(
            select(EventORM)
            .where(EventORM.correlation_id == correlation_id)
            .order_by(EventORM.timestamp.asc())
        )
        return list(result.scalars().all())

    def to_domain(self, record: EventORM) -> Event:
        """ORM -> 领域对象。"""
        return Event(
            id=record.public_id,
            type=EventType(record.type),
            source=record.source,
            timestamp=record.timestamp,
            learner_id=record.learner_public_id,
            data=record.data or {},
            correlation_id=record.correlation_id,
        )
