from datetime import date

from sqlalchemy import select, delete, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from models.driver import Driver
from models.reservation import Reservation


class ReservationDAO:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, reservation_data: dict):
        reservation = Reservation(**reservation_data)
        self.session.add(reservation)
        await self.session.commit()
        return reservation

    async def get_by_spot_and_day_of_week(self, spot_id: int, day: int):
        result = await self.session.execute(
            select(Reservation).where(
                Reservation.parking_spot_id == spot_id,
                Reservation.day_of_week == day
            )
        )
        return result.scalars().all()

    async def get_by_day(self, day: date):
        day_of_week = day.weekday()

        stmt = (
            select(Reservation)
            .join(Driver)
            .where(and_(Reservation.day_of_week == day_of_week,
                        Driver.enabled == True,
                        or_(Driver.absent_until == None, Driver.absent_until <= day)
                        )
                   )
        )
        results = await self.session.execute(stmt)
        return results.scalars().all()

    async def get_by_params(self, filters: dict):
        query = select(Reservation).where(*[
            getattr(Reservation, key) == value
            for key, value in filters.items()
        ])
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_by_params(self, filters: dict):
        query = delete(Reservation).where(*[
            getattr(Reservation, key) == value
            for key, value in filters.items()
        ])
        result = await self.session.execute(query)
        return result.rowcount
