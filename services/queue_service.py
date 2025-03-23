from sqlalchemy.ext.asyncio import AsyncSession

from dao.queue_dao import QueueDAO
from models.driver import Driver


class QueueService:
    def __init__(self, session: AsyncSession):
        self.dao = QueueDAO(session)

    async def get_all(self):
        return await self.dao.get_all()

    async def del_all(self):
        return await self.dao.del_all()

    async def get_driver_queue_index(self, driver: Driver) -> int | None:
        return await self.dao.get_driver_queue_index(driver)

    async def join_queue(self, driver: Driver):
        await self.dao.add_to_queue(driver)

    async def leave_queue(self, driver: Driver):
        await self.dao.del_by_driver(driver)
