import datetime
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
        return queue

    async def add_to_queue(self, driver: Driver) -> Queue:
        new_entry = Queue(
            created=datetime.datetime.now(),
            driver=driver,
            driver_id=driver.id,
        )
        self.session.add(new_entry)
        await self.session.commit()
        return new_entry

    async def get_all(self) -> Sequence[Queue]:
        """Получение всех водителей"""
        result = await self.session.execute(select(Queue).order_by(Queue.created))
        return result.scalars().all()

    async def get_queue_by_driver(self, driver: Driver) -> Queue:
        result = await self.session.execute(select(Queue).where(Queue.driver_id.is_(driver.id)))
        return result.scalar_one_or_none()

    async def del_by_driver(self, driver: Driver):
        await self.session.execute(delete(Queue).where(Queue.driver_id.is_(driver.id)))

    async def del_all(self):
        await self.session.execute(delete(Queue))

    async def is_driver_in_queue(self, driver: Driver) -> bool:
        result = await self.session.execute(select(Queue).where(Queue.driver_id.is_(driver.id)))
        return result.scalar_one_or_none() is not None
