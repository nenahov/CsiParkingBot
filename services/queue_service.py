from sqlalchemy.ext.asyncio import AsyncSession

from dao.queue_dao import QueueDAO


class QueueService:
    def __init__(self, session: AsyncSession):
        self.dao = QueueDAO(session)

    async def get_all(self):
        return await self.dao.get_all()

    async def del_all(self):
        return await self.dao.del_all()
