"""事件持久化服务: 把 Event 写入 events 表(事件溯源)。"""

import logging

from core.event_bus import Event
from db.base import AsyncSessionLocal
from repositories import EventRepository

logger = logging.getLogger(__name__)


class EventPersistenceService:
    """事件溯源持久化服务。

    作为 EventBus 的 persist_callback 注入,每个 publish() 都会先写 DB 再分发。
    """

    def __init__(self) -> None:
        pass

    async def __call__(self, event: Event) -> None:
        async with AsyncSessionLocal() as session:
            repo = EventRepository(session)
            await repo.append(event)
            await session.commit()
