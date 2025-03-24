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
        f"Всего в очереди: {len(queue_all)} человек\n\n"
        # Список позиций и водителей в очереди
        f"{''.join(f'{i + 1}. {queue.driver.title}\n' for i, queue in enumerate(queue_all))}"
    )


@router.message(F.text.regexp(r"(?i)(.*покинуть очередь)|(.*выйти из очереди)"), flags={"check_driver": True})
async def leave_queue(message: Message, session, driver, is_private):
    queue_service = QueueService(session)
    queue_index = await queue_service.get_driver_queue_index(driver)
    if queue_index is None:
        await message.reply(f"Вы не в очереди")
        return
    await queue_service.leave_queue(driver)
    await message.reply(f"Вы были в очереди на {queue_index} месте\nТеперь вы не в очереди")


@router.message(F.text.regexp(r"(?i)(.*встать в очередь)|(.*свободное мест)"), flags={"check_driver": True})
async def join_queue(message: Message, session, driver, is_private):
    queue_service = QueueService(session)
    queue_index = await queue_service.get_driver_queue_index(driver)
    if queue_index is not None:
        await message.reply(f"Вы уже в очереди на {queue_index} месте")
        return
    await queue_service.join_queue(driver)
    queue_index = await queue_service.get_driver_queue_index(driver)
    await message.reply(f"Вы встали в очередь на {queue_index} место")
