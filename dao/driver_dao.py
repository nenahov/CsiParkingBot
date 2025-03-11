from typing import Optional, List

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models.driver import Driver


class DriverDAO:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, chat_id: int, username: Optional[str] = None) -> Driver:
        """Создание нового водителя"""
        driver = Driver(chat_id=chat_id, username=username)
        self.session.add(driver)
        await self.session.commit()
        return driver

    async def get_by_id(self, driver_id: int) -> Optional[Driver]:
        """Получение водителя по ID"""
        result = await self.session.execute(
            select(Driver).where(Driver.id == driver_id)
        )
        return result.scalar_one_or_none()

    async def get_by_chat_id(self, chat_id: int) -> Optional[Driver]:
        """Получение водителя по chat_id"""
        result = await self.session.execute(
            select(Driver).where(Driver.chat_id == chat_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> List[Driver]:
        """Получение всех водителей"""
        result = await self.session.execute(select(Driver))
        return result.scalars().all()

    async def update_username(self, driver_id: int, new_username: str) -> Driver:
        """Обновление username водителя"""
        await self.session.execute(
            update(Driver)
            .where(Driver.id == driver_id)
            .values(username=new_username)
        )
        await self.session.commit()
        return await self.get_by_id(driver_id)

    async def delete(self, driver_id: int) -> None:
        """Удаление водителя"""
        await self.session.execute(
            delete(Driver).where(Driver.id == driver_id))
        await self.session.commit()

    async def driver_exists(self, chat_id: int) -> bool:
        """Проверка существования водителя"""
        result = await self.session.execute(
            select(Driver.id).where(Driver.chat_id == chat_id))
        return result.scalar() is not None
