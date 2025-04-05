import asyncio

from sqlalchemy import insert

from config.database import Base, engine, db_pool
from models.driver import Driver
from models.parking_spot import ParkingSpot


async def insert_test_data():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with db_pool() as session:
        # Парковочные места
        parking_spots = [
            {"id": 12, "x": 408, "y": 49, "width": 49, "height": 99},
            {"id": 18, "x": 918, "y": 198, "width": 49, "height": 99},
            {"id": 19, "x": 867, "y": 198, "width": 49, "height": 99},
            {"id": 20, "x": 816, "y": 198, "width": 49, "height": 99},
            {"id": 21, "x": 765, "y": 198, "width": 49, "height": 99},
            {"id": 22, "x": 714, "y": 198, "width": 49, "height": 99},
            {"id": 23, "x": 663, "y": 198, "width": 49, "height": 99},
            {"id": 24, "x": 612, "y": 198, "width": 49, "height": 99},
            {"id": 25, "x": 561, "y": 198, "width": 49, "height": 99},
            {"id": 26, "x": 510, "y": 198, "width": 49, "height": 99},
            {"id": 27, "x": 459, "y": 198, "width": 49, "height": 99},
            {"id": 35, "x": 918, "y": 298, "width": 49, "height": 99},
            {"id": 36, "x": 867, "y": 298, "width": 49, "height": 99},
            {"id": 37, "x": 816, "y": 298, "width": 49, "height": 99},
            {"id": 38, "x": 765, "y": 298, "width": 49, "height": 99},
            {"id": 39, "x": 714, "y": 298, "width": 49, "height": 99},
            {"id": 74, "x": 1019, "y": 399, "width": 101, "height": 48}
        ]
        await session.execute(insert(ParkingSpot), parking_spots)
        await session.flush()

        # Водители
        drivers = [
            {"id": 12, "chat_id": "-12", "username": "black_loyalty", "title": "Королева И.",
             "description": "Королева Ирина"},
            {"id": 112, "chat_id": "-112", "username": "Горбенко", "title": "Горбенко М.",
             "description": "Горбенко Максим"},
            {"id": 13, "chat_id": "-13", "username": "Алексеев", "title": "Алексеев А.",
             "description": "Алексеев Альберт"},
            {"id": 18, "chat_id": "-18", "username": "Росколодько", "title": "Росколодько И.",
             "description": "Росколодько Иван"},
            {"id": 118, "chat_id": "-118", "username": "Рыбкин", "title": "Рыбкин", "description": "Рыбкин"},
            {"id": 19, "chat_id": "-19", "username": "Насикан", "title": "Насикан В.",
             "description": "Насикан Владимир"},
            {"id": 119, "chat_id": "-119", "username": "Хабибулин", "title": "Хабибулин", "description": "Хабибулин"},
            {"id": 20, "chat_id": "201420475", "username": "Tangorerro", "title": "Тушинский А.",
             "description": "Тушинский Александр"},
            {"id": 120, "chat_id": "-120", "username": "Окишев", "title": "Окишев А.", "description": "Окишев Андрей"},
            {"id": 21, "chat_id": "-21", "username": "Смирнов", "title": "Смирнов", "description": "Смирнов"},
            {"id": 121, "chat_id": "-121", "username": "Глазырина", "title": "Глазырина", "description": "Глазырина"},
            {"id": 22, "chat_id": "-22", "username": "Зиле", "title": "Зиле Т.", "description": "Зиле Татьяна"},
            {"id": 23, "chat_id": "-23", "username": "Онуфриев", "title": "Онуфриев А.",
             "description": "Онуфриев Алексей"},
            {"id": 123, "chat_id": "-123", "username": "Стефаненков", "title": "Стефаненков Д.",
             "description": "Стефаненков Дмитрий"},
            {"id": 24, "chat_id": "-24", "username": "Корчиев", "title": "Корчиев", "description": "Корчиев"},
            {"id": 124, "chat_id": "-124", "username": "Герчиков", "title": "Герчиков", "description": "Герчиков"},
            {"id": 224, "chat_id": "-224", "username": "Надольский", "title": "Надольский",
             "description": "Надольский"},
            {"id": 25, "chat_id": "-25", "username": "Тоноян", "title": "Тоноян", "description": "Тоноян"},
            {"id": 125, "chat_id": "-125", "username": "Щедрович", "title": "Щедрович", "description": "Щедрович"},
            {"id": 225, "chat_id": "-225", "username": "Морозов", "title": "Морозов", "description": "Морозов"},
            {"id": 325, "chat_id": "413159571", "username": "Ванеев", "title": "Ванеев И.",
             "description": "Ванеев Игорь"},
            {"id": 26, "chat_id": "-26", "username": "Артемьев", "title": "Артемьев", "description": "Артемьев"},
            {"id": 126, "chat_id": "-126", "username": "Зубова", "title": "Зубова", "description": "Зубова"},
            {"id": 226, "chat_id": "-226", "username": "Макурина", "title": "Макурина", "description": "Макурина"},
            {"id": 326, "chat_id": "-326", "username": "Сыроватский", "title": "Сыроватский",
             "description": "Сыроватский"},
            {"id": 27, "chat_id": "-27", "username": "Тынчеров", "title": "Тынчеров", "description": "Тынчеров"},
            {"id": 127, "chat_id": "-127", "username": "Иманов", "title": "Иманов", "description": "Иманов"},
            {"id": 227, "chat_id": "-227", "username": "Никитина", "title": "Никитина Д.",
             "description": "Никитина Дарья"},
            {"id": 35, "chat_id": "-35", "username": "Петров", "title": "Петров", "description": "Петров"},
            {"id": 135, "chat_id": "-135", "username": "Шубина", "title": "Шубина", "description": "Шубина"},
            {"id": 235, "chat_id": "-235", "username": "Селезнева", "title": "Селезнева", "description": "Селезнева"},
            {"id": 36, "chat_id": "-36", "username": "Плис", "title": "Плис Ян", "description": "Плис Ян"},
            {"id": 136, "chat_id": "-136", "username": "Смирнов", "title": "Смирнов", "description": "Смирнов"},
            {"id": 236, "chat_id": "-236", "username": "Ершов", "title": "Ершов А.", "description": "Ершов Артем"},
            {"id": 37, "chat_id": "-37", "username": "Лоншакова", "title": "Лоншакова", "description": "Лоншакова"},
            {"id": 137, "chat_id": "-137", "username": "Плис", "title": "Плис", "description": "Плис"},
            {"id": 38, "chat_id": "-38", "username": "Вернигора", "title": "Вернигора Н.",
             "description": "Вернигора Никита"},
            {"id": 238, "chat_id": "-238", "username": "Рассказов", "title": "Рассказов", "description": "Рассказов"},
            {"id": 39, "chat_id": "-39", "username": "Алексеев И", "title": "Алексеев И", "description": "Алексеев И"},
            {"id": 74, "chat_id": "-74", "username": "Апухтин", "title": "Апухтин", "description": "Апухтин"},
            {"id": 174, "chat_id": "-174", "username": "Кульметьев А.", "title": "Кульметьев А.",
             "description": "Кульметьев Антон"}
        ]
        await session.execute(insert(Driver), drivers)

        # Резервации
        # reservations = [
        #     {"day_of_week": 0, "parking_spot_id": 1, "driver_id": 1},
        #     {"day_of_week": 1, "parking_spot_id": 2, "driver_id": 2}
        # ]
        # await session.execute(insert(Reservation), reservations)

        await session.commit()


if __name__ == "__main__":
    asyncio.run(insert_test_data())
    print("Тестовые данные успешно добавлены!")
