from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.parking_spot import ParkingSpot


class ParkingSpotDAO:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self):
        result = await self.session.execute(select(ParkingSpot).order_by(ParkingSpot.id))
        return result.scalars().all()

    async def clear_statuses(self):
        await self.session.execute(update(ParkingSpot).
                                   values(status=None,
                                          current_driver_id=None))
        await self.session.commit()
