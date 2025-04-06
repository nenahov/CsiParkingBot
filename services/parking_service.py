from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from dao.parking_spot_dao import ParkingSpotDAO
from models.driver import Driver
from services.reservation_service import ReservationService


class ParkingService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.dao = ParkingSpotDAO(session)

    async def get_all_spots(self):
        return await self.dao.get_all()

    async def get_spots_with_reservations(self, day: date):
        spots = await self.dao.get_all()
        reservations_data = dict()

        reservations = await ReservationService(self.session).get_by_day(day)
        if reservations:
            for reservation in reservations:
                reservations_data.setdefault(reservation.parking_spot_id, []).append(reservation)

        return spots, reservations_data

    async def clear_statuses(self):
        await self.dao.clear_statuses()

    async def leave_spot(self, driver: Driver):
        await self.dao.leave_spot(driver)

    async def occupy_spot(self, driver, spot_id: int, without_demand=False):
        await self.dao.occupy_spot(driver, spot_id, without_demand)

    async def get_free_spots(self, day_of_week: int):
        return await self.dao.get_free_spots(day_of_week)

    async def get_spot_by_id(self, spot_id: int):
        return await self.dao.get_by_id(spot_id)
