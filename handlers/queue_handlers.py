from aiogram import Router, F
from aiogram.filters import Command, or_f
from aiogram.types import Message

from services.queue_service import QueueService

router = Router()


@router.message(or_f(Command("queue"), F.text.regexp(r"(?i)(.*пока.* очередь)|(.*очередь парковки)")),
                flags={"check_driver": True})
async def queue_command(message: Message, session, driver, is_private):
    queue_service = QueueService(session)
    queue_all = await queue_service.get_all()
    await message.reply(
        f"Текущее состояние очереди\n\n"
        f"Всего в очереди: {len(queue_all)} человек(а)\n\n"
        # Список позиций и водителей в очереди
        f"{''.join(f'• {queue.driver.title}{(" ❗️🏆 ❗️ " + str(queue.spot_id) + " место до " + queue.choose_before.strftime('%H:%M')) if queue.spot_id else ''}\n' for queue in queue_all)}"
    )


@router.message(F.text.regexp(r"(?i)(.*покинуть очередь)|(.*выйти из очереди)"), flags={"check_driver": True})
async def leave_queue(message: Message, session, driver, is_private):
    queue_service = QueueService(session)
    in_queue = await queue_service.is_driver_in_queue(driver)
    if not in_queue:
        await message.reply(f"Вы не в очереди")
        return
    await queue_service.leave_queue(driver)
    await message.reply(f"Теперь вы не в очереди")


@router.message(F.text.regexp(r"(?i)(.*встать в очередь)|(.*хочу свободное место)"), flags={"check_driver": True})
async def join_queue(message: Message, session, driver, is_private):
    queue_service = QueueService(session)
    in_queue = await queue_service.is_driver_in_queue(driver)
    if in_queue:
        await message.reply(f"Вы уже в очереди")
        return
    await queue_service.join_queue(driver)
    await message.reply(f"Вы встали в очередь")
