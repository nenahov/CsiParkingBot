from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command, or_f
from aiogram.types import Message

from services.parking_service import ParkingService
from services.queue_service import QueueService

router = Router()


@router.message(or_f(Command("queue"), F.text.regexp(r"(?i)(.*пока.* очередь)|(.*очередь парковки)")),
                flags={"check_driver": True})
async def queue_command(message: Message, session, driver):
    # Получаем текущий день недели (0 - понедельник, 6 - воскресенье)
    current_day = datetime.today().weekday()
    # Получаем данные для карты
    parking_service = ParkingService(session)
    queue_service = QueueService(session)
    spots, reservations = await parking_service.get_spots_with_reservations(current_day)
    queue_all = await queue_service.get_all()
    await message.answer(
        f"Показываем текущее состояние очереди {queue_all}"
    )

# text_handlers.add_handler(r"(отсутствую|не приеду|буду отсутствовать)\s+(\d+)\s+(день|дня|дней)",
#                           lambda message, match, session, driver: k1(message, match))
