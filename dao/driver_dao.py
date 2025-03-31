from typing import Optional, Sequence

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

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
            select(Driver).where(Driver.id.is_(driver_id))
        )
        return result.scalar_one_or_none()

    async def get_by_chat_id(self, chat_id: int) -> Optional[Driver]:
        """Получение водителя по chat_id"""
        result = await self.session.execute(
            select(Driver)
            # .options(selectinload(Driver.parking_spots))
            .where(Driver.chat_id.is_(chat_id))
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> Sequence[Driver]:
        """Получение всех водителей"""
        result = await self.session.execute(select(Driver))
        return result.scalars().all()

    async def delete(self, driver_id: int) -> None:
        """Удаление водителя"""
        await self.session.execute(
            delete(Driver).where(Driver.id.is_(driver_id)))

    async def driver_exists(self, chat_id: int) -> bool:
        """Проверка существования водителя"""
        result = await self.session.execute(
            select(Driver.id).where(Driver.chat_id.is_(chat_id)))
        return result.scalar() is not None

    async def remove_attribute_for_all(self, key: str) -> None:
        """Удаление атрибута у всех водителей"""
        stmt = (
            update(Driver)
            .values(
                attributes=func.json_remove(
                    Driver.attributes,
                    f'$.{key}'  # Путь к ключу
                )
            )
        )

        await self.session.execute(stmt)
