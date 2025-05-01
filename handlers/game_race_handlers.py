import json
from io import BytesIO

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, FSInputFile, InputMediaPhoto, BufferedInputFile
from aiogram.utils.formatting import Bold
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from handlers.driver_callback import add_button, MyCallback
from models.driver import Driver
from models.user_audit import UserActionType
from services.audit_service import AuditService
from services.driver_service import DriverService
from services.notification_sender import send_alarm
from services.param_service import ParamService
from utils.cars_generator import draw_start_race_track

MAX_PLAYERS = 10

router = Router()


async def get_state(chat_id: int, session):
    race_state = await ParamService(session).get_parameter('race_state', '{}')
    states = json.loads(race_state)
    return states.get(str(chat_id), None)


async def save_state(chat_id: int, game_state, session):
    race_state = await ParamService(session).get_parameter('race_state', '{}')
    states = json.loads(race_state)
    states[str(chat_id)] = game_state
    await ParamService(session).set_parameter('race_state', json.dumps(states))


@router.message(
    F.text.regexp(r"(?i).*да начнется гонка"),
    flags={"lock_operation": "race", "long_operation": "upload_photo", "check_admin": True, "check_driver": True})
async def game_race(message: Message, session: AsyncSession, driver: Driver, current_day, is_private):
    if is_private:
        await message.answer("Команда недоступна в личных сообщениях.")
        return

    game_state = await get_state(message.chat.id, session)
    if game_state is None:
        game_state = list()
        await save_state(message.chat.id, game_state, session)
    content, builder, icons = await get_game_message(game_state, session)
    await message.answer_photo(show_caption_above_media=False,
                               photo=await get_media(game_state, icons),
                               reply_markup=builder.as_markup(),
                               **content.as_kwargs(text_key="caption", entities_key="caption_entities"))
    await AuditService(session).log_action(driver.id, UserActionType.GAME, current_day, 0,
                                           f'{driver.title} Начинает игру "Гонки"')


@router.callback_query(MyCallback.filter(F.action == "join_race"),
                       flags={"lock_operation": "race", "long_operation": "upload_photo", "check_driver": True})
async def join_race_callback(callback: CallbackQuery, callback_data: MyCallback, session, driver: Driver, current_day):
    game_state = await get_state(callback.message.chat.id, session)
    if game_state is None:
        await send_alarm(callback, "⚠️ Начните Новую игру!")
        return

    game_state = await get_state(callback.message.chat.id, session)
    if game_state is None:
        await send_alarm(callback, "⚠️ Начните Новую игру!")
        return

    if len(game_state) >= MAX_PLAYERS:
        await send_alarm(callback, "Состав заезда определен, начните заезд!")
        return

    if driver.id in game_state:
        await send_alarm(callback, "⚠️ Вы уже участник заезда!")
        return

    game_state.append(driver.id)
    await save_state(callback.message.chat.id, game_state, session)

    content, builder, icons = await get_game_message(game_state, session)
    await callback.message.edit_media(
        media=InputMediaPhoto(show_caption_above_media=False,
                              # media=BufferedInputFile(photo.getvalue(), filename="carousel.png")),
                              media=await get_media(game_state, icons)),
        reply_markup=builder.as_markup(),
        **content.as_kwargs(text_key="caption", entities_key="caption_entities"))


async def get_media(game_state, icons):
    if len(game_state) < 5:
        return FSInputFile("./pics/racing.jpg")
    track = draw_start_race_track(icons, bg_color=(120, 120, 120), track_length=len(game_state) * 120)
    img_buffer = BytesIO()
    track.save(img_buffer, format="PNG")
    img_buffer.seek(0)
    return BufferedInputFile(img_buffer.getvalue(), filename="race.png")


async def get_game_message(game_state, session):
    content = Bold(f"Игра «Гонки».\n\n")
    icons = []
    for i, player_id in enumerate(game_state):
        player = await DriverService(session).get_by_id(player_id)
        content += f"{i + 1}. {player.title}\n"
        icons.append(player.attributes.get("car_index", player.id))
    builder = await get_keyboard_by_game_state(game_state)
    return content, builder, icons


async def get_keyboard_by_game_state(game_state):
    builder = InlineKeyboardBuilder()
    if len(game_state) < MAX_PLAYERS:
        add_button("🏎️ Вступить в гонку (плата 💟 5 кармы)", "join_race", 0, builder)
    if len(game_state) >= 5:
        add_button("🏁 Начать гонку!", "start_race", 0, builder)
    builder.adjust(1)
    return builder
