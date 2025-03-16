from typing import List

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models.driver import Driver
from models.queue import Queue


class QueueDAO:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, driver: Driver, spot_id: int) -> Queue:
        """Создание нового водителя"""
        queue = Queue(driver=driver, spot_id=spot_id, driver_id=driver.id)
        self.session.add(queue)
        await self.session.commit()
        return queue

    async def get_all(self) -> List[Queue]:
        """Получение всех водителей"""
        result = await self.session.execute(select(Queue))
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
