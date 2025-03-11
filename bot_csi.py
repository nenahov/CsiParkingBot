import asyncio
import os

from aiogram import Bot, Dispatcher

from config.database import create_database
from handlers import main_handlers, reservation_handlers, map_handlers


async def main():
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    dp = Dispatcher()

    await create_database()

    # await insert_test_data()

    dp.include_router(main_handlers.router)
    dp.include_router(map_handlers.router)
    dp.include_router(reservation_handlers.router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
