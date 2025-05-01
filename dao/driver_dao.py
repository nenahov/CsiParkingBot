from datetime import date
from typing import Optional, Sequence

from sqlalchemy import select, update, delete, func, cast, Integer, and_, or_
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

    async def get_absent_drivers_for_auto_karma(self, is_working_day: bool) -> Sequence[Driver]:
        # Выбираем водителей, которые отсутствуют на текущую дату (или сегодня выходной)
        target_date = date.today()
        # И у которых в атрибуте есть значение "plus" >= 0
        sql = (select(Driver)
               .filter(Driver.enabled.is_(True))
               .filter(func.json_extract(Driver.attributes, '$.plus').isnot(None))
               .filter(func.json_extract(Driver.attributes, '$.plus') >= 0))
        if is_working_day:
            sql = (sql
                   .filter(Driver.absent_until.is_not(None))
                   .filter(Driver.absent_until > target_date))
        result = await self.session.execute(sql)
        return result.scalars().all()

    async def get_active_partner_drivers(self, driver_id: int, target_date: date) -> set[Driver]:
        """
        Возвращает список водителей, имеющих общие парковочные места с заданным водителем,
        исключая самого водителя.
        """
        # 1. Определяем все id парковочных мест, с которыми связан данный водитель
        stmt = (
            select(ParkingSpot.id)
            .join(ParkingSpot.drivers)
            .where(Driver.id.is_(driver_id))
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
            .where(and_(ParkingSpot.id.in_(parking_spot_ids),
                        Driver.id != driver_id,
                        Driver.enabled.is_(True),
                        or_(
                            Driver.absent_until.is_(None),
                            Driver.absent_until <= target_date
                        ))
                   )
            .distinct()  # Чтобы избежать дублей, если водитель встречается в нескольких парковках
        )
        result = await self.session.execute(stmt)
        partner_drivers = result.scalars().all()

        return set(partner_drivers)
