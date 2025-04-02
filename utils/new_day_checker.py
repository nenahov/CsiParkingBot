import logging
import random
from datetime import datetime, timedelta

from services.driver_service import DriverService
from services.parking_service import ParkingService
from services.queue_service import QueueService
from services.reservation_service import ReservationService

logger = logging.getLogger(__name__)


async def check_current_day(session, param_service):
    # Получаем текущий день
    new_day_offset = await param_service.get_parameter("new_day_offset", "4")
    current_day = (datetime.now() + timedelta(hours=int(new_day_offset))).date()

    current_day_str = current_day.strftime('%d.%m.%Y')
    old_day = await param_service.get_parameter("current_day")
    if not old_day or old_day != current_day_str:
        # смена дня
        print(f"Наступил новый день: {current_day_str}")
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

    return current_day
