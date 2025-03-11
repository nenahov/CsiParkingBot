import asyncio

from sqlalchemy import insert

from config.database import Base, engine, async_session_maker
from models.driver import Driver
from models.parking_spot import ParkingSpot
from models.reservation import Reservation


async def insert_test_data():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        # Парковочные места
        parking_spots = [
            {"x": 100, "y": 200, "width": 80, "height": 50},
            {"x": 200, "y": 200, "width": 80, "height": 50},
            {"x": 300, "y": 200, "width": 80, "height": 50}
        ]
        await session.execute(insert(ParkingSpot), parking_spots)

        # Водители
        drivers = [
            {"chat_id": "12345", "username": "user1"},
            {"chat_id": "67890", "username": "user2"}
        ]
        await session.execute(insert(Driver), drivers)

        await session.commit()

        # Резервации
        reservations = [
            {"day_of_week": 0, "parking_spot_id": 1, "driver_id": 1},
            {"day_of_week": 1, "parking_spot_id": 2, "driver_id": 2}
        ]
        await session.execute(insert(Reservation), reservations)

        await session.commit()


if __name__ == "__main__":
    asyncio.run(insert_test_data())
    print("Тестовые данные успешно добавлены!")
