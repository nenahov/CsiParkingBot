import asyncio
import os

from aiogram import Bot, Dispatcher

from config.database import create_database, db_pool
from handlers import main_handlers, reservation_handlers, map_handlers, user_handlers, queue_handlers, admin_handlers, \
    game_handlers, commands_handlers
from middlewares.admin_check import AdminCheckMiddleware
from middlewares.db import DbSessionMiddleware
from middlewares.driver_check import DriverCheckMiddleware
from middlewares.long_operation import LongOperationMiddleware
from middlewares.my_callback_check import MyCallbackCheckMiddleware
from middlewares.new_day_check import NewDayCheckMiddleware


async def main():
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    # Запускаем бота и пропускаем все накопленные входящие
    # Да, этот метод можно вызвать даже если у вас поллинг
    await bot.delete_webhook(drop_pending_updates=True)

    dp = Dispatcher()

    await create_database()

    # await insert_test_data()

    # Register middlewares
    dp.message.middleware(LongOperationMiddleware())
    dp.message.middleware(DbSessionMiddleware(db_pool))
    dp.message.middleware(NewDayCheckMiddleware())
    dp.message.middleware(DriverCheckMiddleware())
    dp.message.middleware(AdminCheckMiddleware())
    dp.callback_query.middleware(MyCallbackCheckMiddleware())
    dp.callback_query.middleware(DbSessionMiddleware(db_pool))
    dp.callback_query.middleware(NewDayCheckMiddleware())
    dp.callback_query.middleware(DriverCheckMiddleware())
    dp.callback_query.middleware(AdminCheckMiddleware())

    dp.include_router(queue_handlers.router)
    dp.include_router(user_handlers.router)
    dp.include_router(map_handlers.router)
    dp.include_router(reservation_handlers.router)
    dp.include_router(admin_handlers.router)
    dp.include_router(main_handlers.router)
    dp.include_router(commands_handlers.router)
    dp.include_router(game_handlers.router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
