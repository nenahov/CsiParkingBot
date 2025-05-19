import logging
import random
from datetime import datetime, timedelta, time

from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from config import constants
from dao.queue_dao import QueueDAO
from handlers.driver_callback import add_button
from models.driver import Driver
from models.queue import Queue
from services.param_service import ParamService
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

    async def get_queue_by_driver(self, driver: Driver) -> Queue | None:
        return await self.dao.get_queue_by_driver(driver)

    async def join_queue(self, driver: Driver):
        await self.dao.add_to_queue(driver)

    async def leave_queue(self, driver: Driver):
        await self.dao.del_by_driver(driver)

    async def check_free_spots(self, bot, current_day):
        # Если сейчас от 19:00 до 21:00 или от 01:00 до 07:00, то выйти из процедуры
        now = datetime.now()
        if constants.new_day_begin_hour <= now.hour < constants.new_day_queue_hour or now.hour in constants.quiet_hours:
            return

        current_week_day = current_day.weekday()

        queue = list(await self.dao.get_all())
        missed = [q for q in queue if q.choose_before is not None and q.choose_before <= datetime.now()]
        for q in missed:
            logger.info(f"{q.driver.description} пропустил очередь на место {q.spot_id}")
            builder = InlineKeyboardBuilder()
            add_button("✋ Покинуть очередь", "leave-queue", q.driver.chat_id, builder)
            add_button("ℹ️ Статус", "show-status", q.driver.chat_id, builder)
            builder.adjust(1)
            try:
                await bot.send_message(chat_id=q.driver.chat_id,
                                       text=f"❌ Вы пропустили вашу очередь.\n\nМесто {q.spot_id} будет разыграно заново.",
                                       reply_markup=builder.as_markup())
            except Exception as e:
                logger.error(f"Error sending notification to {q.driver.title}: {e}")

            q.choose_before = None
            q.spot_id = None

        spots = list(await ParkingService(self.session).get_free_spots(current_week_day, current_day))

        # Сначала оставляем только места, которые можно брать для очереди (прошел таймаут после действий владельца)
        spots = [s for s in spots if s.for_queue_after is None or s.for_queue_after <= datetime.now()]

        # Оставляем только места, которые еще не участвуют в очереди
        spots = [s for s in spots if not any(q.spot_id == s.id for q in queue)]

        # Потом оставляем только людей, которым еще не предложено место
        queue = [q for q in queue if q.choose_before is None]

        # Разыгрываем места среди владельцев места, которые стоят в очереди
        for spot in spots:
            owners_in_queue = [q for q in queue if q.driver_id in [d.id for d in spot.drivers]]
            await self.raffle_off_spot_among_filtered_queue(bot, now, spot, owners_in_queue, spots, queue)

        # Разыгрываем оставшиеся места среди очереди
        while queue and spots:
            spot = random.choice(spots)
            await self.raffle_off_spot_among_filtered_queue(bot, now, spot, queue, spots, queue)

    async def raffle_off_spot_among_filtered_queue(self, bot, now, spot, filtered_queue, spots, queue):
        add_weight_karma = int(await ParamService(self.session).get_parameter("add_weight_karma", "0"))
        while spot in spots and filtered_queue:
            # Выбираем случайного человека из очереди и случайное свободное место
            q = random.choices(filtered_queue, weights=[
                max(1, add_weight_karma + q.driver.get_karma() + q.driver.attributes.get("add_weight_karma", 0))
                for q in filtered_queue], k=1)[0]

            # Обновляем данные для выбранного элемента очереди:
            q.spot_id = spot.id
            # к текущему времени добавляем 10 минут, но если получившиеся время от 19:00 до 09:00 следующего дня, то ставим 09:00 следующего дня
            choose_before = datetime.now() + timedelta(minutes=10)
            if choose_before.hour >= constants.new_day_begin_hour:
                choose_before = datetime.combine(now.date() + timedelta(days=1), time(9, 0))
            elif choose_before.hour < 8 or (choose_before.hour == 8 and choose_before.minute < (60 - 10)):
                choose_before = datetime.combine(now.date(), time(9, 0))
            q.choose_before = choose_before

            builder = InlineKeyboardBuilder()
            add_button(f"Занять ⚪️ {spot.id}", "occupy-spot-from-queue", q.driver.chat_id, builder, spot.id)
            add_button("✋ Покинуть очередь", "leave-queue", q.driver.chat_id, builder)
            builder.adjust(1)
            logger.info(
                f"{q.driver.description} может занять место {q.spot_id} до {q.choose_before.strftime('%d.%m.%Y %H:%M')}")
            try:
                # Удаляем выбранного человека
                filtered_queue.remove(q)
                if q in queue:
                    queue.remove(q)
                await bot.send_message(chat_id=q.driver.chat_id,
                                       text=f"Появилось свободное место: {spot.id}.\n\nНажмите на кнопку с местом до {q.choose_before.strftime('%H:%M')}.",
                                       reply_markup=builder.as_markup())
                # Удаляем выбранное место из дальнейшего выбора
                spots.remove(spot)
            except Exception as e:
                q.spot_id = None
                logger.error(f"Error sending notification to {q.driver.title}: {e}")
                logger.info(
                    f"{q.driver.description} не получил уведомление. Место {spot.id} будет разыграно заново.")
