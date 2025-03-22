from typing import Sequence

from sqlalchemy import select, delete
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

    async def add_to_queue(self, driver: Driver, spot_id: int) -> Queue:
        last_position = await self.get_last_position()
        new_entry = Queue(
            driver=driver,
            spot_id=spot_id,
            driver_id=driver.id,
            position=last_position + 1 if last_position else 1
        )
        self.session.add(new_entry)
        await self.session.commit()
        return new_entry

    async def get_last_position(self) -> int | None:
        result = await self.session.execute(select(Queue.position).order_by(Queue.position.desc()).limit(1))
        return result.scalar_one_or_none()

    async def get_all(self) -> Sequence[Queue]:
        """Получение всех водителей"""
        result = await self.session.execute(select(Queue).order_by(Queue.position, Queue.created))
        return result.scalars().all()

    async def get_queue_by_driver(self, driver: Driver) -> Queue:
        result = await self.session.execute(select(Queue).where(Queue.driver_id == driver.id))
        return result.scalar_one_or_none()

    async def del_by_driver(self, driver: Driver):
        await self.session.execute(delete(Queue).where(Queue.driver_id == driver.id))

    async def del_all(self):
        await self.session.execute(delete(Queue))
