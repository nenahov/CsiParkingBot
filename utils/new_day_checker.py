import asyncio
import logging
import random
from datetime import datetime, timedelta

from handlers.user_handlers import get_status_message
from services.driver_service import DriverService
from services.notification_sender import NotificationSender, EventType
from services.parking_service import ParkingService
from services.queue_service import QueueService
from services.reservation_service import ReservationService

logger = logging.getLogger(__name__)


async def check_current_day(bot, session, param_service):
    # Получаем текущий день
    new_day_offset = await param_service.get_parameter("new_day_offset", "5")
    current_day = (datetime.now() + timedelta(hours=int(new_day_offset))).date()

    current_day_str = current_day.strftime('%d.%m.%Y')
    old_day = await param_service.get_parameter("current_day")

    if old_day and old_day == current_day_str:
        return current_day

    # смена дня
    logger.info(f"Наступил новый день: {current_day_str}")

    # очищаем очереди и состояние парковки
    queue_service = QueueService(session)
    await queue_service.del_all()

    parking_service = ParkingService(session)
    await parking_service.clear_statuses()

    reservation_service = ReservationService(session)
    await reservation_service.delete_duplicate_reservations(current_day)

    driver_service = DriverService(session)
    # await driver_service.remove_attribute_for_all("test")

    drivers = await driver_service.get_all()
    for driver in drivers:
        driver.attributes["plus"] = random.randint(0, 100)

    # устанавливаем текущий день
    await param_service.set_parameter("current_day", current_day_str)
    await session.commit()

    notification_sender = NotificationSender(bot)
    for driver in drivers:
        if await notification_sender.send_to_driver(EventType.NEW_DAY, driver, driver,
                                                    my_date=current_day.strftime('%d.%m.%Y')):
            content, builder = await get_status_message(driver, True, session, current_day)
            await bot.send_message(driver.chat_id, **content.as_kwargs(), reply_markup=builder.as_markup())
            await asyncio.sleep(0.1)

    return current_day
