from datetime import date

from dao.reservation_dao import ReservationDAO


class ReservationService:
    def __init__(self, session):
        self.session = session
        self.dao = ReservationDAO(session)

    async def create_reservation(self, reservation_data: dict):
        # Сначала удалим другие резервы этого водителя на этот день недели
        await self.delete_reservation(reservation_data.get('driver_id'), reservation_data.get('day_of_week'))
        # Добавим новый резерв
        return await self.dao.create(reservation_data)

    async def delete_reservation(self, driver_id: int, day_of_week: int):
        deleted = await self.dao.delete_by_params({
            "driver_id": driver_id,
            "day_of_week": day_of_week
        })

    async def check_time_overlap(self, new_reservation: dict):
        existing = await self.dao.get_by_spot_and_day_of_week(
            new_reservation['parking_spot_id'],
            new_reservation['day_of_week']
        )

        # Реализация проверки пересечения временных интервалов
        # TODO

    async def get_spot_reservations(self, spot_id: int, day_of_week: int):
        return await self.dao.get_by_spot_and_day_of_week(spot_id, day_of_week)

    async def get_by_day(self, day: date):
        return await self.dao.get_by_day(day)

    async def delete_duplicate_reservations(self, target_date: date):
        result = await self.dao.delete_duplicate_reservations(target_date)
        print(f"{result} дубликатов удалено")
        return result
