import datetime
import logging
import random
from typing import Callable, Awaitable, Dict, Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from services.driver_service import DriverService
from services.param_service import ParamService
from services.parking_service import ParkingService
from services.queue_service import QueueService
from services.reservation_service import ReservationService

logger = logging.getLogger(__name__)


class NewDayCheckMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any],
    ) -> Any:
        """
        Проверяет, наступило ли время обнулить очередь и состояние парковки
        """
        param_service = data.get("param_service")
        if not param_service:
            session = data["session"]
            param_service = ParamService(session)
            data["param_service"] = param_service

        # Получаем текущий день
        new_day_offset = await param_service.get_parameter("new_day_offset", "4")
        new_day = (datetime.datetime.now() + datetime.timedelta(hours=int(new_day_offset))).date()
        data["current_day"] = new_day
        current_day = new_day.strftime('%d.%m.%Y')

        old_day = await param_service.get_parameter("current_day")
        if not old_day or old_day != current_day:
            # смена дня
            print(f"Наступил новый день: {current_day}")
            logger.info(f"Наступил новый день: {current_day}")

            # очищаем очереди и состояние парковки
            queue_service = QueueService(data["session"])
            await queue_service.del_all()

            parking_service = ParkingService(data["session"])
            await parking_service.clear_statuses()

            reservation_service = ReservationService(data["session"])
            await reservation_service.delete_duplicate_reservations(new_day)

            driver_service = DriverService(data["session"])
            # await driver_service.remove_attribute_for_all("test")

            drivers = await driver_service.get_all()
            for driver in drivers:
                driver.attributes["plus"] = random.randint(0, 100)

            # устанавливаем текущий день
            await param_service.set_parameter("current_day", current_day)

        return await handler(event, data)
