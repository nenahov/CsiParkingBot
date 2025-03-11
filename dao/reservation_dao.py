from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.reservation import Reservation


class ReservationDAO:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, reservation_data: dict):
        reservation = Reservation(**reservation_data)
        self.session.add(reservation)
        await self.session.commit()
        return reservation

    async def get_by_spot_and_day(self, spot_id: int, day: int):
        result = await self.session.execute(
            select(Reservation).where(
                Reservation.parking_spot_id == spot_id,
                Reservation.day_of_week == day
            )
        )
        return result.scalars().all()

    async def get_by_params(self, filters: dict):
        query = select(Reservation).where(*[
            getattr(Reservation, key) == value
            for key, value in filters.items()
        ])
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
