from aiogram import Router, F
from aiogram.filters import Command, or_f
from aiogram.types import (
    Message,
    CallbackQuery,
    InputRichBlockButtons,
    InputRichBlockParagraph,
    InputRichBlockSectionHeading,
    InputRichBlockTable,
    InputRichMessage,
    RichBlockTableCell,
    RichMessageButton,
    RichTextBold,
    RichTextUnion,
)
from sqlalchemy.ext.asyncio import AsyncSession

from handlers.driver_callback import MyCallback
from handlers.user_handlers import show_status_callback
from models.driver import Driver
from models.user_audit import UserActionType
from services.audit_service import AuditService
from services.notification_sender import send_alarm
from services.queue_service import QueueService
from services.telegram_ui import answer_rich

router = Router()


@router.message(or_f(Command("queue"), F.text.regexp(r"(?i)(.*пока.* очередь)|(.*очередь парковки)")),
                flags={"lock_operation": "queue", "check_driver": True})
async def queue_command(message: Message, session, driver, is_private):
    queue_service = QueueService(session)
    queue_all = await queue_service.get_all()
    rows = [[
        _queue_cell("№", header=True),
        _queue_cell("Водитель", header=True),
        _queue_cell("Место", header=True),
        _queue_cell("Забрать до", header=True),
    ]]
    fallback_lines = [f"Текущая очередь: {len(queue_all)} человек(а)"]
    for index, entry in enumerate(queue_all, start=1):
        name: RichTextUnion = entry.driver.description
        if entry.driver_id == driver.id:
            name = [RichTextBold(text="Вы — "), entry.driver.description]
        rows.append([
            _queue_cell(str(index), align="center"),
            _queue_cell(name),
            _queue_cell(str(entry.spot_id) if entry.spot_id else "—", align="center"),
            _queue_cell(entry.choose_before.strftime("%H:%M") if entry.choose_before else "—",
                        align="center"),
        ])
        suffix = (
            f" — место {entry.spot_id} до {entry.choose_before.strftime('%H:%M')}"
            if entry.spot_id and entry.choose_before
            else ""
        )
        fallback_lines.append(f"{index}. {entry.driver.description}{suffix}")

    actions = []
    if await queue_service.is_driver_in_queue(driver):
        actions.append(
            RichMessageButton(
                text="✋ Покинуть очередь",
                callback_data=MyCallback(
                    action="leave-queue", user_id=driver.chat_id, spot_id=None,
                    day_num=None, event_type=None, bool_value=None,
                ).pack(),
            )
        )
    else:
        actions.append(
            RichMessageButton(
                text="🙋 Встать в очередь",
                callback_data=MyCallback(
                    action="join-queue", user_id=driver.chat_id, spot_id=None,
                    day_num=None, event_type=None, bool_value=None,
                ).pack(),
            )
        )
    blocks = [
        InputRichBlockSectionHeading(text="Текущее состояние очереди", size=1),
        InputRichBlockParagraph(text=f"Всего в очереди: {len(queue_all)} человек(а)"),
        InputRichBlockTable(cells=rows, is_bordered=True, is_striped=True, is_compact=True),
        InputRichBlockButtons(buttons=actions, align="center"),
    ]
    await answer_rich(
        message,
        InputRichMessage(blocks=blocks),
        fallback_text="\n".join(fallback_lines),
    )


def _queue_cell(text: RichTextUnion, *, header: bool = False, align: str = "left"):
    return RichBlockTableCell(
        text=text,
        align=align,
        valign="middle",
        is_header=True if header else None,
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
        await send_alarm(message, f"⚠️ Вы не в очереди", personal=True)
        return
    await queue_service.leave_queue(driver)
    await send_alarm(message, f"👋 Теперь вы не в очереди", personal=True)
    await AuditService(session).log_action(driver.id, UserActionType.LEAVE_QUEUE, current_day,
                                           description=f"{driver.description} покинул очередь")


@router.message(F.text.regexp(r"(?i)(.*встать в очередь)|(.*хочу свободное место)"),
                flags={"lock_operation": "queue", "check_driver": True})
async def join_queue(message, session, driver, current_day):
    queue_service = QueueService(session)
    in_queue = await queue_service.is_driver_in_queue(driver)
    if in_queue:
        await send_alarm(message, f"⚠️ Вы уже в очереди", personal=True)
    else:
        # Если уже есть место, которое вы занимаете, то никакой очереди!
        await session.refresh(driver, ["current_spots"])
        if driver.get_occupied_spots():
            await send_alarm(
                message,
                f"⚠️ Вы уже занимаете место: {[spot.id for spot in driver.get_occupied_spots()]}",
                personal=True,
            )
        else:
            await queue_service.join_queue(driver)
            await send_alarm(message, f"✅ Вы встали в очередь", personal=True)
            await AuditService(session).log_action(driver.id, UserActionType.JOIN_QUEUE, current_day,
                                                   description=f"{driver.description} встал в очередь")
