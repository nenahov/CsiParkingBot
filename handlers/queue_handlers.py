from aiogram import Router, F
from aiogram.filters import Command, or_f
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from handlers.driver_callback import MyCallback
from handlers.user_handlers import show_status_callback
from models.driver import Driver
from models.user_audit import UserActionType
from services.audit_service import AuditService
from services.notification_sender import send_alarm
from services.queue_service import QueueService

router = Router()


@router.message(or_f(Command("queue"), F.text.regexp(r"(?i)(.*пока.* очередь)|(.*очередь парковки)")),
                flags={"lock_operation": "queue", "check_driver": True})
async def queue_command(message: Message, session, driver, is_private):
    queue_service = QueueService(session)
    queue_all = await queue_service.get_all()
    await message.reply(
        f"Текущее состояние очереди\n\n"
        f"Всего в очереди: {len(queue_all)} человек(а)\n"
        # Список позиций и водителей в очереди
        f"{''.join(f'• {queue.driver.description}{(" ❗️🏆❗️ " + str(queue.spot_id) + " место до " + queue.choose_before.strftime('%H:%M')) if queue.spot_id else ''}\n' for queue in queue_all)}"
    )


@router.callback_query(MyCallback.filter(F.action == "leave-queue"),
                       flags={"lock_operation": "queue", "check_driver": True, "check_callback": True})
async def leave_queue_callback(callback: CallbackQuery, session: AsyncSession, driver: Driver, current_day, is_private):
    await leave_queue(callback, session, driver, current_day)
    await show_status_callback(callback, session, driver, current_day, is_private)


@router.callback_query(MyCallback.filter(F.action == "join-queue"),
                       flags={"lock_operation": "queue", "check_driver": True, "check_callback": True})
async def join_queue_callback(callback: CallbackQuery, session: AsyncSession, driver: Driver, current_day, is_private):
    await join_queue(callback, session, driver, current_day)
    await show_status_callback(callback, session, driver, current_day, is_private)


@router.message(F.text.regexp(r"(?i)(.*покинуть очередь)|(.*выйти из очереди)"),
                flags={"lock_operation": "queue", "check_driver": True})
async def leave_queue(message, session, driver, current_day):
    queue_service = QueueService(session)
    in_queue = await queue_service.is_driver_in_queue(driver)
    if not in_queue:
        await send_alarm(message, f"⚠️ Вы не в очереди")
        return
    await queue_service.leave_queue(driver)
    await send_alarm(message, f"👋 Теперь вы не в очереди")
    await AuditService(session).log_action(driver.id, UserActionType.LEAVE_QUEUE, current_day,
                                           description=f"{driver.description} покинул очередь")


@router.message(F.text.regexp(r"(?i)(.*встать в очередь)|(.*хочу свободное место)"),
                flags={"lock_operation": "queue", "check_driver": True})
async def join_queue(message, session, driver, current_day):
    queue_service = QueueService(session)
    in_queue = await queue_service.is_driver_in_queue(driver)
    if in_queue:
        await send_alarm(message, f"⚠️ Вы уже в очереди")
    else:
        # Если уже есть место, которое вы занимаете, то никакой очереди!
        await session.refresh(driver, ["current_spots"])
        if driver.get_occupied_spots():
            await send_alarm(message, f"⚠️ Вы уже занимаете место: {[spot.id for spot in driver.get_occupied_spots()]}")
        else:
            await queue_service.join_queue(driver)
            await send_alarm(message, f"✅ Вы встали в очередь")
            await AuditService(session).log_action(driver.id, UserActionType.JOIN_QUEUE, current_day,
                                                   description=f"{driver.description} встал в очередь")
