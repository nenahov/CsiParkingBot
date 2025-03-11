from sqlalchemy.ext.asyncio import AsyncSession

from dao.parking_spot_dao import ParkingSpotDAO
from services.reservation_service import ReservationService


class ParkingService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.dao = ParkingSpotDAO(session)

    async def get_all_spots(self):
        return await self.dao.get_all()

    async def get_spots_with_reservations(self, day_of_week):
        spots = await self.dao.get_all()
        reservations_data = {}

        for spot in spots:
            reservations = await ReservationService(self.session).get_by_spot_and_day(
                spot.id,
                day_of_week
            )
            if reservations:
                reservations_data[spot.id] = reservations

        return spots, reservations_data
