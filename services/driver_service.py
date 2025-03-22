from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from dao.driver_dao import DriverDAO
from models.driver import Driver


class DriverService:
    def __init__(self, session: AsyncSession):
        self.dao = DriverDAO(session)

    async def register_driver(self, chat_id: int, username: str, title: str, desc: str) -> Driver:
        if await self.dao.driver_exists(chat_id):
            raise ValueError("Driver already exists")
        return await self.dao.create(chat_id, username, title=title, desc=desc, enabled=False)

    async def get_by_chat_id(self, chat_id: int):
        return await self.dao.get_by_chat_id(chat_id)

    async def update_absent_until(self, driver_id: int, absent_until: date):
        return await self.dao.update_absent_until(driver_id, absent_until)
