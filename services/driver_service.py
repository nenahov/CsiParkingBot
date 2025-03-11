from sqlalchemy.ext.asyncio import AsyncSession

from dao.driver_dao import DriverDAO
from models.driver import Driver


class DriverService:
    def __init__(self, session: AsyncSession):
        self.dao = DriverDAO(session)

    async def register_driver(self, chat_id: int, username: str) -> Driver:
        if await self.dao.driver_exists(chat_id):
            raise ValueError("Driver already exists")
        return await self.dao.create(chat_id, username)

    async def get_by_chat_id(self, chat_id: int):
        return await self.dao.get_by_chat_id(chat_id)
