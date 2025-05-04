import pickle
import re
from math import ceil

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.utils.formatting import Text, Bold, Italic, Code
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from handlers.driver_callback import add_button, MyCallback
from models.driver import Driver
from models.user_audit import UserActionType
from services.audit_service import AuditService
from services.driver_service import DriverService
from services.notification_sender import send_alarm
from utils.game_parking_utils import generate_map_with_constraints, STONE, FINISH, EMPTY, FUEL, CAR, TREASURE

states = dict()
router = Router()


def get_state(driver: Driver):
    result = states.get(driver.id)
    try:
        if not result:
            result = pickle.loads(driver.attributes.get('p_state', '').encode('latin1'))
    except:
        return None
    return result


def save_state(driver: Driver, game_state):
    driver.attributes['p_state'] = pickle.dumps(game_state).decode('latin1')
    states[driver.id] = game_state


@router.callback_query(F.data.startswith("game_parking"),
                       flags={"check_driver": True})
async def game_parking(callback: CallbackQuery, session: AsyncSession, driver: Driver, current_day, is_private):
    content = Bold(f"Игра «Доберись до парковки».\n\n")
    content += (f"Вы на {CAR} должны добраться до {FINISH} (+1 💟).\n"
                "Следите за уровнем топлива! (если закончится - конец игры и -1 💟)\n"
                f"По дороге можете заправиться на {FUEL} (после заправки - исчезает);\n"
                "Домики - препятствия;\n"
                f"{EMPTY} - дорога;\n"
                f"{STONE} - теряете 10% топлива;\n"
                f"{TREASURE} - получаете +1 💟;\n"
                f"{FINISH} - финиш!\n\n")

    await callback.message.answer(**content.as_kwargs())
    game_state = get_state(driver)
    if game_state is None or game_state.is_end_game():
        game_state = generate_map_with_constraints(17, 13)
        save_state(driver, game_state)
        driver.attributes["karma"] = max(0, driver.attributes.get("karma", 0) - 1)
        await AuditService(session).log_action(driver.id, UserActionType.GAME_KARMA, current_day, -1,
                                               f"{driver.title} начал игру Доберись до парковки за -1 кармы")

    content = Text("E ", Italic(f"{'▓' * ceil(game_state.fuel / 10)}{'▒' * ceil((100 - game_state.fuel) / 10)}"),
                   f"  F ⛽️\n\n")
    content += game_state.get_map_section()

    builder = await get_keyboard_by_game_state(driver, game_state)

    await callback.message.answer(**content.as_kwargs(), reply_markup=builder.as_markup())
    await callback.answer()
    await AuditService(session).log_action(driver.id, UserActionType.GAME, current_day, 0,
                                           f"{driver.title} играет в Доберись до парковки")


async def get_keyboard_by_game_state(driver, game_state):
    builder = InlineKeyboardBuilder()
    if game_state.is_end_game():
        return builder

    add_button("✖️", "pass", driver.chat_id, builder)
    await add_move_button(game_state, "⬆️", builder, driver, 0, -1)
    add_button("✖️", "pass", driver.chat_id, builder)
    await add_move_button(game_state, "⬅️", builder, driver, -1, 0)
    add_button("🚘", "pass", driver.chat_id, builder)
    await add_move_button(game_state, "➡️", builder, driver, 1, 0)
    add_button("✖️", "pass", driver.chat_id, builder)
    await add_move_button(game_state, "⬇️", builder, driver, 0, 1)
    add_button("✖️", "pass", driver.chat_id, builder)
    builder.adjust(3, 3, 3, 1)
    return builder


async def add_move_button(game_state, arrow, builder, driver, dx, dy):
    if game_state.is_wall(dx, dy):
        add_button("✖️", "pass", driver.chat_id, builder)
    else:
        add_button(arrow, "p_move", driver.chat_id, builder, spot_id=dx, day_num=dy)


@router.callback_query(MyCallback.filter(F.action == "pass"),
                       flags={"check_driver": True, "check_callback": True})
async def pass_callback(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(MyCallback.filter(F.action == "p_move"),
                       flags={"check_driver": True, "check_callback": True})
async def move_callback(callback: CallbackQuery, callback_data: MyCallback, session, driver: Driver, current_day):
    game_state = get_state(driver)
    if game_state is None:
        await send_alarm(callback, "⚠️ Начните Новую игру!")
        return
    item = game_state.move(callback_data.spot_id, callback_data.day_num)
    save_state(driver, game_state)
    if item is not None and item == TREASURE:
        driver.attributes["karma"] = driver.attributes.get("karma", 0) + 1
        await send_alarm(callback, "🫶 +1 к Вашей карме!")
        await AuditService(session).log_action(driver.id, UserActionType.GAME_KARMA, current_day, 1,
                                               f"{driver.title} получил +1 к карме в игре Доберись до парковки")

    if not await check_end_game(callback, game_state, driver, session, current_day):
        content = Text("E ", Italic(f"{'▓' * ceil(game_state.fuel / 10)}{'▒' * (10 - ceil(game_state.fuel / 10))}"),
                       f"  F ⛽️\n\n")
        content += game_state.get_map_section()
        builder = await get_keyboard_by_game_state(driver, game_state)
        await callback.message.edit_text(**content.as_kwargs(), reply_markup=builder.as_markup())


async def check_end_game(callback, game_state, driver, session, current_day):
    if game_state.is_end_game():
        if game_state.is_win():
            await callback.message.edit_text(text=("🏆 Вы успешно доехали до парковки!\n\n"
                                                   "◻️◻️◻️◻️◻️◻️◻️\n"
                                                   "◻️🅿️🅿️🅿️🅿️◻️◻️\n"
                                                   "◻️🅿️◻️◻️🅿️◻️◻️\n"
                                                   "◻️🅿️🅿️🅿️🅿️◻️◻️\n"
                                                   "◻️🅿️◻️◻️◻️◻️◻️\n"
                                                   "◻️🅿️◻️◻️🚘◻️◻️\n"
                                                   "◻️◻️◻️◻️◻️◻️◻️"))
            await send_alarm(callback, "🎉 Поздравляем! Вы победили!")
            await AuditService(session).log_action(driver.id, UserActionType.GAME, current_day, 1,
                                                   f"{driver.title} доехал до парковки в игре Доберись до парковки")
            driver.attributes["karma"] = driver.attributes.get("karma", 0) + 1
            await AuditService(session).log_action(driver.id, UserActionType.GAME_KARMA, current_day, 1,
                                                   f"{driver.title} успешно закончил игру Доберись до парковки и получил +1 кармы")

        else:
            await callback.message.edit_text(text=("😅 У вас закончилось топливо!\n\n"
                                                   "◼️◼️◼️◼️◼️◼️◼️\n"
                                                   "◼️🅿️🅿️🅿️🅿️◼️◼️\n"
                                                   "◼️🅿️◼️◼️🅿️◼️◼️\n"
                                                   "◼️🅿️🅿️🅿️🅿️◼️◼️\n"
                                                   "◼️🅿️◼️◼️◼️◼️◼️\n"
                                                   "◼️🅿️◼️◼️🚘◼️◼️\n"
                                                   "◼️◼️◼️◼️◼️◼️◼️"))
            await send_alarm(callback, "❌ Игра окончена")
            await AuditService(session).log_action(driver.id, UserActionType.GAME, current_day, -1,
                                                   f"У {driver.title} закончилось топливо в игре Доберись до парковки")
            driver.attributes["karma"] = max(0, driver.attributes.get("karma", 0) - 1)
            await AuditService(session).log_action(driver.id, UserActionType.GAME_KARMA, current_day, -1,
                                                   f"{driver.title} проиграл в игре Доберись до парковки и лишился -1 кармы")

        return True
    return False


@router.message(
    F.text.regexp(r"(?i).*показать Доберись до парковки.* (\d+)").as_("match"),
    flags={"check_admin": True, "check_driver": True})
async def show_game_map(message: Message, session: AsyncSession, driver: Driver, current_day, is_private,
                        match: re.Match):
    driver_id = int(match.group(1))
    gamer = await DriverService(session).get_by_id(driver_id)
    if gamer is None:
        await message.answer("🚫 Пользователь не найден")
        return
    game_state = get_state(gamer)
    if game_state is None:
        await message.answer("🚫 Игра не начата")
        return
    content = Code(game_state.get_map())
    await message.answer(**content.as_kwargs())
