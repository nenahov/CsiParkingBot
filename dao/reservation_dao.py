from datetime import date

from sqlalchemy import select, delete, and_, or_, func, exists
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

    async def get_by_spot_and_day_of_week(self, spot_id: int, day_of_week: int):
        result = await self.session.execute(
            select(Reservation).
            where(
                Reservation.parking_spot_id.is_(spot_id),
                Reservation.day_of_week.is_(day_of_week)
            ).
            order_by(Reservation.id)
        )
        return result.scalars().all()

    async def get_by_day(self, day: date):
        day_of_week = day.weekday()

        stmt = (
            select(Reservation)
            .join(Driver)
            .where(and_(Reservation.day_of_week.is_(day_of_week),
                        Driver.enabled == True,
                        or_(Driver.absent_until.is_(None), Driver.absent_until <= day)
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

    async def delete_duplicate_reservations(self, target_date):
        min_ids_subq = (
            select(
                Reservation.day_of_week,
                Reservation.parking_spot_id,
                func.min(Reservation.id).label("min_id")
            )
            .group_by(Reservation.day_of_week, Reservation.parking_spot_id)
            .subquery()
        )

        driver_condition = exists(
            select(Driver.id).where(
                Driver.id.is_(Reservation.driver_id),
                or_(
                    Driver.absent_until.is_(None),
                    Driver.absent_until <= target_date
                )
            )
        )

        delete_stmt = (
            delete(Reservation)
            .where(
                Reservation.id > select(min_ids_subq.c.min_id)
                .where(
                    Reservation.day_of_week.is_(min_ids_subq.c.day_of_week),
                    Reservation.parking_spot_id.is_(min_ids_subq.c.parking_spot_id)
                )
                .scalar_subquery()
            )
            .where(driver_condition)
            .execution_options(
                synchronize_session="fetch",
                is_delete_using=True
            )
        )
        await self.session.commit()
        result = await self.session.execute(delete_stmt)
        await self.session.commit()
        return result.rowcount
