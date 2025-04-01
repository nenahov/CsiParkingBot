from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.parking_spot import ParkingSpot, SpotStatus


class ParkingSpotDAO:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self):
        result = await self.session.execute(
            select(ParkingSpot).where(ParkingSpot.status.is_not(SpotStatus.HIDEN)).order_by(ParkingSpot.id))
        return result.scalars().all()

    async def clear_statuses(self):
        await self.session.execute(update(ParkingSpot).
                                   where(ParkingSpot.status.is_not(SpotStatus.HIDEN)).
                                   values(status=None,
                                          current_driver_id=None))

    async def leave_spot(self, driver):
        await self.session.execute(update(ParkingSpot).
                                   where(ParkingSpot.current_driver_id.is_(driver.id)).
                                   values(status=SpotStatus.FREE,
                                          current_driver_id=None))

    async def occupy_spot(self, driver, spot_id: int, without_demand=True):
        await self.session.execute(update(ParkingSpot).
                                   where(ParkingSpot.id.is_(spot_id)).
                                   values(
            status=SpotStatus.OCCUPIED_WITHOUT_DEMAND if without_demand else SpotStatus.OCCUPIED,
            current_driver_id=driver.id))
