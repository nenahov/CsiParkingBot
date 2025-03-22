from datetime import date
from typing import Optional, Sequence

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.driver import Driver


class DriverDAO:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, chat_id: int, username: Optional[str] = None, title: Optional[str] = None,
                     desc: Optional[str] = None,
                     enabled: bool = False, ) -> Driver:
        """Создание нового водителя"""
        driver = Driver(chat_id=chat_id, username=username, title=title, description=desc, enabled=enabled)
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
            select(Driver).options(selectinload(Driver.parking_spots)).where(Driver.chat_id == chat_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> Sequence[Driver]:
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

    async def update_absent_until(self, driver_id: int, absent_until: date) -> Driver:
        """Обновление absent_until водителя"""
        await self.session.execute(
            update(Driver)
            .where(Driver.id == driver_id)
            .values(absent_until=absent_until)
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
