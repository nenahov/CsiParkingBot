import asyncio
import logging
import random
from datetime import datetime, timedelta

from config import constants
from handlers.user_handlers import get_status_message
from models.user_audit import UserActionType
from services.audit_service import AuditService
from services.driver_service import DriverService
from services.holiday_service import HolidayService
from services.notification_sender import NotificationSender, EventType
from services.parking_service import ParkingService
from services.queue_service import QueueService
from services.reservation_service import ReservationService
from services.weather_service import WeatherService

logger = logging.getLogger(__name__)


async def check_current_day(bot, session, param_service):
    # Получаем текущий день
    current_day = (datetime.now() + timedelta(hours=int(constants.new_day_offset))).date()

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
        driver.attributes["plus"] = random.randint(1, 100)

    # устанавливаем текущий день
    await param_service.set_parameter("current_day", current_day_str)
    is_working_day, holiday = await HolidayService().get_day_info(current_day)
    await param_service.set_parameter("current_day_is_working_day", str(is_working_day))
    await param_service.set_parameter("current_day_holiday", holiday)
    await session.commit()

    weather = await WeatherService().get_weather_content(current_day)

    # уведомляем всех водителей
    notification_sender = NotificationSender(bot)
    for driver in drivers:
        if await notification_sender.send_to_driver(EventType.NEW_DAY if is_working_day else EventType.NEW_HOLIDAY,
                                                    driver, driver,
                                                    add_message=weather,
                                                    my_date=current_day.strftime('%a %d.%m.%Y'),
                                                    txt=(holiday + '\n\n') if holiday else ""):
            content, builder = await get_status_message(driver, True, session, current_day)
            await bot.send_message(driver.chat_id, **content.as_kwargs(), reply_markup=builder.as_markup())
            await asyncio.sleep(0.1)

    return current_day


async def check_auto_karma_for_absent(bot, session, param_service, current_day):
    hour = datetime.now().hour
    if hour >= constants.new_day_begin_hour or hour < constants.new_day_auto_karma_hour:
        return

    old_day = await param_service.get_parameter("current_day_auto_karma")
    current_day_str = current_day.strftime('%d.%m.%Y')
    if old_day and old_day == current_day_str:
        return

    await param_service.set_parameter("current_day_auto_karma", current_day_str)
    await session.commit()
    is_working_day = (await param_service.get_parameter("current_day_is_working_day")).lower() in ("yes", "true", "t",
                                                                                                   "1")
    logger.debug(f"is_working_day = {is_working_day}")

    driver_service = DriverService(session)
    drivers = await driver_service.get_absent_drivers_for_auto_karma(is_working_day)
    for driver in drivers:
        try:
            await bot.send_message(chat_id=driver.chat_id, text="🎲 Вы не нажали на Розыгрыш кармы сегодня."
                                                                "\n\n🫶 Но т.к. "
                                                                f"{'Вы уехали' if is_working_day else 'сегодня выходной'}"
                                                                ", мы сделаем это за Вас!")
            data = await bot.send_dice(chat_id=driver.chat_id, emoji=random.choice(['🎲', '🎯', '🏀', '⚽', '🎳']))
            driver.attributes["plus"] = -1
            driver.attributes["karma"] = driver.attributes.get("karma", 0) + data.dice.value
            await  bot.send_message(chat_id=driver.chat_id,
                                    text=f"💟 Вы получили +{data.dice.value} в карму. /status"
                                         f"\n\nЗавтра будет шанс получить еще.")
            logger.info(f"Авторозыгрыш кармы для {driver.description}: +{data.dice.value}")
            await AuditService(session).log_action(driver.id, UserActionType.DRAW_KARMA, current_day, data.dice.value,
                                                   f"Авторозыгрыш кармы для {driver.description}: +{data.dice.value}; стало {driver.attributes["karma"]}")

            await session.commit()
        except Exception as e:
            logger.error(f"Ошибка авторозыгрыша кармы для {driver.description}: {e}")
