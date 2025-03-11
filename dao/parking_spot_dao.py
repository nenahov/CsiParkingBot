from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.parking_spot import ParkingSpot


class ParkingSpotDAO:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self):
        result = await self.session.execute(select(ParkingSpot))
        return result.scalars().all()
