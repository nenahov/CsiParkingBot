from sqlalchemy.ext.asyncio import AsyncSession

from dao.queue_dao import QueueDAO


class QueueService:
    def __init__(self, session: AsyncSession):
        self.dao = QueueDAO(session)

    # async def register_driver(self, chat_id: int, username: str, title: str, desc: str) -> Driver:
    #     if await self.dao.driver_exists(chat_id):
    #         raise ValueError("Driver already exists")
    #     return await self.dao.create(chat_id, username, title=title, desc=desc, enabled=False)

    async def get_all(self):
        return await self.dao.get_all()
