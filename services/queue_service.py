import logging
import random
from datetime import datetime, timedelta

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from dao.queue_dao import QueueDAO
from models.driver import Driver
from services.parking_service import ParkingService

logger = logging.getLogger(__name__)

class QueueService:
    def __init__(self, session: AsyncSession):
        self.dao = QueueDAO(session)
        self.session = session

    async def get_all(self):
        return await self.dao.get_all()

    async def del_all(self):
        return await self.dao.del_all()

    async def is_driver_in_queue(self, driver: Driver) -> bool:
        return await self.dao.is_driver_in_queue(driver)

    async def join_queue(self, driver: Driver):
        await self.dao.add_to_queue(driver)

    async def leave_queue(self, driver: Driver):
        await self.dao.del_by_driver(driver)

    async def check_free_spots(self, bot, current_day):
        # Если сейчас от 19:00 до 21:00 или от 01:00 до 07:00, то выйти из процедуры
        now = datetime.now()
        if 19 <= now.hour < 21 or 1 <= now.hour < 7:
            return

        current_week_day = current_day.weekday()

        queue = list(await self.dao.get_all())
        missed = [q for q in queue if q.choose_before is not None and q.choose_before <= datetime.now()]
        for q in missed:
            logger.info(f"{q.driver.description} пропустил очередь на место {q.spot_id}")
            builder = InlineKeyboardBuilder()
            builder.add(
                InlineKeyboardButton(text="✋ Покинуть очередь", callback_data="leave-queue_" + str(q.driver.chat_id)))
            builder.add(InlineKeyboardButton(text="ℹ️ Статус", callback_data='show-status_' + str(q.driver.chat_id)))
            builder.adjust(1)
            await bot.send_message(chat_id=q.driver.chat_id,
                                   text=f"❌ Вы пропустили вашу очередь.\n\nМесто {q.spot_id} будет разыграно заново.",
                                   reply_markup=builder.as_markup())
            q.choose_before = None
            q.spot_id = None

        # Оставляем только людей, которым еще не предложено место
        queue = [q for q in queue if q.choose_before is None]

        spots = list(await ParkingService(self.session).get_free_spots(current_week_day))
        # Оставляем только места, которые еще не участвуют в очереди
        spots = [s for s in spots if not any(q.spot_id == s.id for q in queue)]

        while queue and spots:
            # Выбираем случайного человека из очереди и случайное свободное место
            q = random.choice(queue)
            spot = random.choice(spots)

            # Обновляем данные для выбранного элемента очереди:
            q.spot_id = spot.id
            q.choose_before = datetime.now() + timedelta(minutes=10)

            builder = InlineKeyboardBuilder()
            builder.add(InlineKeyboardButton(text=f"⚪️ {spot.id}",
                                             callback_data="occupy-spot_" + str(q.driver.chat_id) + "_" + str(spot.id)))
            builder.add(
                InlineKeyboardButton(text="✋ Покинуть очередь", callback_data="leave-queue_" + str(q.driver.chat_id)))
            builder.adjust(1)
            await bot.send_message(chat_id=q.driver.chat_id,
                                   text=f"Появилось свободное место: {spot.id}.\n\nМесто будет доступно до {q.choose_before.strftime('%d.%m.%Y %H:%M')}.",
                                   reply_markup=builder.as_markup())
            logger.info(
                f"{q.driver.description} может занять место {q.spot_id} до {q.choose_before.strftime('%d.%m.%Y %H:%M')}")
            # Удаляем выбранного человека и выбранное место из дальнейшего выбора
            queue.remove(q)
            spots.remove(spot)
