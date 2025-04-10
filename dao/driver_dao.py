from typing import Optional, Sequence

from sqlalchemy import select, update, delete, func, cast, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from models.driver import Driver
from models.parking_spot import ParkingSpot


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

    async def get_top_karma_drivers(self, limit: int) -> Sequence[Driver]:
        result = await self.session.execute(
            select(Driver)
            .filter(func.json_extract(Driver.attributes, '$.karma').isnot(None))
            # Извлекаем значение как число и сортируем по убыванию
            .order_by(cast(func.json_extract(Driver.attributes, '$.karma'), Integer).desc())
            .limit(limit))
        return result.scalars().all()

    async def get_partner_drivers(self, driver_id: int) -> set[Driver]:
        """
        Возвращает список водителей, имеющих общие парковочные места с заданным водителем,
        исключая самого водителя.
        """
        # 1. Определяем все id парковочных мест, с которыми связан данный водитель
        stmt = (
            select(ParkingSpot.id)
            .join(ParkingSpot.drivers)
            .where(Driver.id == driver_id)
        )
        result = await self.session.execute(stmt)
        parking_spot_ids = [row[0] for row in result.all()]

        if not parking_spot_ids:
            return set()  # Если у водителя нет парковочных мест, возвращаем пустой список

        # 2. Находим всех водителей, которые связаны с указанными парковочными местами,
        # исключая исходного водителя
        stmt = (
            select(Driver)
            .join(Driver.parking_spots)
            .where(ParkingSpot.id.in_(parking_spot_ids))
            .where(Driver.id != driver_id)
            .distinct()  # Чтобы избежать дублей, если водитель встречается в нескольких парковках
        )
        result = await self.session.execute(stmt)
        partner_drivers = result.scalars().all()

        return set(partner_drivers)
