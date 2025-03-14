from dao.reservation_dao import ReservationDAO


class ReservationService:
    def __init__(self, session):
        self.session = session
        self.dao = ReservationDAO(session)

    async def create_reservation(self, reservation_data: dict):
        if await self.check_time_overlap(reservation_data):
            raise ValueError("Time overlap detected")
        return await self.dao.create(reservation_data)

    async def check_time_overlap(self, new_reservation: dict):
        existing = await self.dao.get_by_spot_and_day(
            new_reservation['parking_spot_id'],
            new_reservation['day_of_week']
        )

        # Реализация проверки пересечения временных интервалов
        # TODO

    async def get_by_spot_and_day(self, spot_id, day_of_week):
        return await self.dao.get_by_spot_and_day(spot_id, day_of_week)

    async def get_spot_reservations(self, spot_id: int, day: int):
        return await self.dao.get_by_spot_and_day(spot_id, day)

    async def delete_reservation(self, driver_id: int, spot_id: int, day: int):
        deleted = await self.dao.delete_by_params({
            "driver_id": driver_id,
            "parking_spot_id": spot_id,
            "day_of_week": day
        })
        if deleted > 0:
            await self.session.commit()
