from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.parking_spot import ParkingSpot, SpotStatus


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

    async def leave_spot(self, driver):
        await self.session.execute(update(ParkingSpot).
                                   where(ParkingSpot.current_driver_id == driver.id).
                                   values(status=SpotStatus.FREE,
                                          current_driver_id=None))
        await self.session.commit()
