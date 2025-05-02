import json
from io import BytesIO

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, FSInputFile, BufferedInputFile
from aiogram.utils.formatting import Bold, Spoiler, as_key_value
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from handlers.driver_callback import add_button, MyCallback
from models.driver import Driver
from models.user_audit import UserActionType
from services.audit_service import AuditService
from services.driver_service import DriverService
from services.notification_sender import send_alarm
from services.param_service import ParamService
from utils.cars_generator import draw_start_race_track, create_race_gif

PLACE_PERCENT = {1: 40, 2: 30, 3: 20}

MIN_PLAYERS = 5
MAX_PLAYERS = 10
FEE = 5

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


async def remove_state(chat_id: int, game_state, session):
    race_state = await ParamService(session).get_parameter('race_state', '{}')
    states = json.loads(race_state)
    states[str(chat_id)] = None
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
        await AuditService(session).log_action(driver.id, UserActionType.GAME, current_day, 0,
                                               f'{driver.title} Начинает игру "Гонки"')
    content, builder, players = await get_game_message(game_state, session)
    await message.answer_photo(show_caption_above_media=False,
                               photo=await get_media(game_state, players),
                               reply_markup=builder.as_markup(),
                               **content.as_kwargs(text_key="caption", entities_key="caption_entities"))


@router.callback_query(MyCallback.filter(F.action == "join_race"),
                       flags={"lock_operation": "race",
                              "long_operation": "upload_photo",
                              "check_driver": True})
async def join_race_callback(callback: CallbackQuery, callback_data: MyCallback, session, driver: Driver, current_day):
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

    karma = driver.attributes.get("karma", 0)
    if karma < FEE:
        await send_alarm(callback, "⚠️ Недостаточно кармы!")
        return

    driver.attributes["karma"] = karma - FEE
    await AuditService(session).log_action(driver.id, UserActionType.GAME_KARMA, current_day, -FEE,
                                           f"{driver.title} Будет участвовать в заезде и заплатил -{FEE} кармы")

    game_state.append(driver.id)
    await save_state(callback.message.chat.id, game_state, session)

    content, builder, players = await get_game_message(game_state, session)
    await callback.message.answer_photo(show_caption_above_media=False,
                                        photo=await get_media(game_state, players),
                                        reply_markup=builder.as_markup(),
                                        **content.as_kwargs(text_key="caption", entities_key="caption_entities"))
    try:
        await callback.message.delete()
    except:
        pass


@router.callback_query(MyCallback.filter(F.action == "start_race"),
                       flags={"lock_operation": "race",
                              "long_operation": "upload_video",
                              "check_admin": True,
                              "check_driver": True})
async def start_race_callback(callback: CallbackQuery, callback_data: MyCallback, session, driver: Driver, current_day):
    chat_id = callback.message.chat.id
    game_state = await get_state(chat_id, session)
    if game_state is None:
        await send_alarm(callback, "⚠️ Начните Новую игру!")
        return

    if len(game_state) < MIN_PLAYERS:
        await send_alarm(callback, "⚠️ Недостаточно гонщиков в заезде!")
        return

    await AuditService(session).log_action(driver.id, UserActionType.GAME, current_day, 0,
                                           f'{driver.title} Начинает заезд в игре "Гонки"')

    content, _, players = await get_game_message(game_state, session)
    winners = create_race_gif(players, chat_id=chat_id,
                              output_path=f"race_{chat_id}.gif", frame_count=400, duration=2)
    medals = {1: "🥇", 2: "🥈", 3: "🥉", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣", 10: "🔟"}
    count = len(game_state)
    total = FEE * count
    for idx, player_idx in enumerate(winners):
        place = idx + 1
        player = players[player_idx]
        content += f"{medals.get(place, place)} .. "
        content += Spoiler(f"{player.title:…<20}")
        prize = total * PLACE_PERCENT.get(place, 0) // 100
        if prize != 0:
            player.attributes["karma"] = player.attributes.get("karma", 0) + prize
            await AuditService(session).log_action(player.id, UserActionType.GAME_KARMA, current_day, prize,
                                                   f"{player.title} За {place} место в заезде получил {prize:+d} кармы")

        content += '\n'

    await callback.message.answer_animation(animation=FSInputFile(f"race_{chat_id}.mp4"), supports_streaming=True)
    await callback.message.answer(**content.as_kwargs())
    await remove_state(chat_id, game_state, session)


async def get_media(game_state, players):
    if len(game_state) < MIN_PLAYERS:
        return FSInputFile("./pics/racing.jpg")
    track = draw_start_race_track(players, bg_color=(120, 120, 120), track_length=len(game_state) * 120)
    img_buffer = BytesIO()
    track.save(img_buffer, format="PNG")
    img_buffer.seek(0)
    return BufferedInputFile(img_buffer.getvalue(), filename="race.png")


async def get_game_message(game_state, session):
    content = Bold(f"🏁 Игра «Гонки» 🏎️\n\n")
    count = len(game_state)
    total = FEE * count
    content += as_key_value("Количество участников", count)
    content += '\n'
    if count >= MIN_PLAYERS:
        content += as_key_value("\nЗа 🥇 место выигрыш", f"{total * PLACE_PERCENT.get(1, 0) // 100} 💟")
        content += as_key_value("\nЗа 🥈 место выигрыш", f"{total * PLACE_PERCENT.get(2, 0) // 100} 💟")
        content += as_key_value("\nЗа 🥉 место выигрыш", f"{total * PLACE_PERCENT.get(3, 0) // 100} 💟")
        content += '\n\n'
    players = []
    for idx, player_id in enumerate(game_state):
        player = await DriverService(session).get_by_id(player_id)
        players.append(player)
        if count < MIN_PLAYERS:
            content += f"{idx + 1}. {player.title}\n"
    builder = await get_keyboard_by_game_state(game_state)
    return content, builder, players


async def get_keyboard_by_game_state(game_state):
    builder = InlineKeyboardBuilder()
    if len(game_state) < MAX_PLAYERS:
        add_button(f"Участвовать (плата 💟 {FEE} кармы)", "join_race", 0, builder)
    if len(game_state) >= MIN_PLAYERS:
        add_button("🏁 Начать гонку!", "start_race", 0, builder)
    builder.adjust(1)
    return builder
