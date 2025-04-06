from datetime import date

from sqlalchemy import select, update, or_, exists, not_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.driver import Driver
from models.parking_spot import ParkingSpot, SpotStatus
from models.reservation import Reservation


class ParkingSpotDAO:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, spot_id: int) -> ParkingSpot | None:
        result = await self.session.execute(
            select(ParkingSpot).where(ParkingSpot.id.is_(spot_id)))
        return result.scalar_one_or_none()

    async def get_all(self):
        result = await self.session.execute(
            select(ParkingSpot).where(ParkingSpot.status.is_not(SpotStatus.HIDDEN)).order_by(ParkingSpot.id))
        return result.scalars().all()

    async def clear_statuses(self):
        await self.session.execute(update(ParkingSpot).
                                   where(ParkingSpot.status.is_not(SpotStatus.HIDDEN)).
                                   values(status=None,
                                          current_driver_id=None))

    async def leave_spot(self, driver):
        await self.session.execute(update(ParkingSpot).
                                   where(ParkingSpot.current_driver_id.is_(driver.id)).
                                   values(status=SpotStatus.FREE))

    async def occupy_spot(self, driver, spot_id: int, without_demand=True):
        await self.session.execute(update(ParkingSpot).
        where(ParkingSpot.id.is_(spot_id)).
        values(
            status=SpotStatus.OCCUPIED_WITHOUT_DEMAND if without_demand else SpotStatus.OCCUPIED,
            current_driver_id=driver.id))

    async def get_by_spot_and_day_of_week(self, spot_id: int, day_of_week: int):
        result = await self.session.execute(
            select(Reservation).
            where(
                Reservation.parking_spot_id.is_(spot_id),
                Reservation.day_of_week.is_(day_of_week)
            ).
            order_by(Reservation.id)
        )
        return result.scalars().all()

    async def get_free_spots(self, day_of_week: int, day: date):
        # получить места с пустым статусом или со статусом Free
        # и у которых нет резервирования в этот день недели
        result = await self.session.execute(
            select(ParkingSpot).
            where(
                or_(
                    ParkingSpot.status.is_(None),
                    ParkingSpot.status.is_(SpotStatus.FREE)
                ),
                not_(exists(
                    select(Reservation)
                    .join(Driver)
                    .where(and_(Reservation.day_of_week.is_(day_of_week),
                                Reservation.parking_spot_id.is_(ParkingSpot.id),
                                Driver.enabled == True,
                                or_(Driver.absent_until.is_(None), Driver.absent_until <= day)
                                )
                           )
                ))
            )
        )
        return result.scalars().all()
