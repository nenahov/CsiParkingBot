import json
import re

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.utils.formatting import Bold, Code
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from handlers.driver_callback import add_button, MyCallback
from models.driver import Driver
from models.user_audit import UserActionType
from services.audit_service import AuditService
from services.driver_service import DriverService
from services.notification_sender import send_alarm
from services.param_service import ParamService

states = dict()
router = Router()


async def get_state(chat_id: int, session):
    global states
    try:
        if not states:
            race_state = await ParamService(session).get_parameter('race_state', '{}')
            states = json.loads(race_state)
    except:
        pass
    return states.get(chat_id)


async def save_state(chat_id: int, game_state, session):
    states[chat_id] = game_state
    await ParamService(session).set_parameter('race_state', json.dumps(states))


@router.message(
    F.text.regexp(r"(?i).*да начнется гонка"),
    flags={"check_admin": True, "check_driver": True})
async def game_race(message: Message, session: AsyncSession, driver: Driver, current_day, is_private):
    if is_private:
        await message.answer("Команда недоступна в личных сообщениях.")
        return

    content = Bold(f"Игра «Доберись до парковки».\n\n")

    builder = await get_keyboard_by_game_state(driver, None)

    await message.answer(**content.as_kwargs(), reply_markup=builder.as_markup())
    await AuditService(session).log_action(driver.id, UserActionType.GAME, current_day, 0,
                                           f'{driver.title} Начинает игру "Гонки"')


async def get_keyboard_by_game_state(driver, game_state):
    builder = InlineKeyboardBuilder()

    add_button("🏎️ Вступить в гонку", "join_race", driver.chat_id, builder)
    builder.adjust(1)
    return builder


@router.callback_query(MyCallback.filter(F.action == "join_race"),
                       flags={"check_driver": True})
async def move_callback(callback: CallbackQuery, callback_data: MyCallback, session, driver: Driver, current_day):
    game_state = await get_state(callback.message.chat.id, session)
    if game_state is None:
        await send_alarm(callback, "⚠️ Начните Новую игру!")
        return


@router.message(
    F.text.regexp(r"(?i).*показать Доберись до парковки.* (\d+)").as_("match"),
    flags={"check_admin": True, "check_driver": True})
async def show_game_map(message: Message, session: AsyncSession, driver: Driver, current_day, is_private,
                        match: re.Match):
    driver_id = int(match.group(1))
    gamer = await DriverService(session).get_by_id(driver_id)
    if gamer is None:
        await message.answer("🚫 Пользователь не найден")
        return
    game_state = await get_state(gamer, session)
    if game_state is None:
        await message.answer("🚫 Игра не начата")
        return
    content = Code(game_state.get_map())
    await message.answer(**content.as_kwargs())
