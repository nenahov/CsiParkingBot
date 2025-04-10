from datetime import date

from sqlalchemy import Sequence
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

    async def get_all(self):
        return await self.dao.get_all()

    async def get_by_chat_id(self, chat_id: int):
        return await self.dao.get_by_chat_id(chat_id)

    async def remove_attribute_for_all(self, key: str):
        await self.dao.remove_attribute_for_all(key)

    async def get_top_karma_drivers(self, limit: int = 10) -> Sequence[Driver]:
        return await self.dao.get_top_karma_drivers(limit)

    async def get_partner_drivers(self, driver_id: int, target_date: date) -> set[Driver]:
        return await self.dao.get_partner_drivers(driver_id, target_date)
