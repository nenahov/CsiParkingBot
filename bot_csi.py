import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config.database import create_database, db_pool
from handlers import main_handlers, reservation_handlers, map_handlers, user_handlers, queue_handlers, admin_handlers, \
    game_handlers, commands_handlers
from middlewares.admin_check import AdminCheckMiddleware
from middlewares.db import DbSessionMiddleware
from middlewares.driver_check import DriverCheckMiddleware
from middlewares.logging_middleware import LoggingMiddleware
from middlewares.long_operation import LongOperationMiddleware
from middlewares.my_callback_check import MyCallbackCheckMiddleware
from middlewares.new_day_check import NewDayCheckMiddleware
from services.param_service import ParamService
from services.queue_service import QueueService
from utils.new_day_checker import check_current_day


async def main():
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    # Запускаем бота и пропускаем все накопленные входящие
    # Да, этот метод можно вызвать даже если у вас поллинг
    await bot.delete_webhook(drop_pending_updates=True)

    dp = Dispatcher()

    await create_database()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_message_to_queue, "interval", seconds=1 * 60, args=(bot,))
    logging.getLogger('apscheduler.executors.default').setLevel(logging.WARNING)
    scheduler.start()

    # await insert_test_data()

    # Register middlewares
    dp.message.middleware(LoggingMiddleware())
    dp.message.middleware(LongOperationMiddleware())
    dp.message.middleware(DbSessionMiddleware(db_pool))
    dp.message.middleware(NewDayCheckMiddleware())
    dp.message.middleware(DriverCheckMiddleware())
    dp.message.middleware(AdminCheckMiddleware())
    dp.callback_query.middleware(LoggingMiddleware())
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


async def send_message_to_queue(bot: Bot):
    async with db_pool() as session:
        try:
            current_day = await check_current_day(session, ParamService(session))
            await QueueService(session).check_free_spots(bot, current_day)
            await session.commit()
        except Exception as e:
            await session.rollback()  # Откатываем сессию при ошибке
            raise e  # Поднимаем исключение дальше
        finally:
            await session.close()  # Закрываем сессию


if __name__ == "__main__":
    asyncio.run(main())
