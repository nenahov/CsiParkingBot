import json
import os
import random
from io import BytesIO

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, FSInputFile, BufferedInputFile
from aiogram.utils.formatting import Bold, Spoiler, as_key_value, Code, Text, HashTag
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
from utils.game_race_utils import GameState, generate_game_with_weather_forecast

PLACE_PERCENT = {1: 35, 2: 25, 3: 17, 4: 12, 5: 8}

MIN_PLAYERS = 7
MAX_PLAYERS = 12
FEE = 5

router = Router()


async def get_state(chat_id: int, session) -> GameState | None:
    race_state = await ParamService(session).get_parameter('race_state', '{}')
    states = json.loads(race_state)
    state_dict = states.get(str(chat_id), None)
    if state_dict is None:
        return None
    state = GameState.from_dict(state_dict)
    return state


async def save_state(chat_id: int, game_state: GameState, session):
    race_state = await ParamService(session).get_parameter('race_state', '{}')
    states = json.loads(race_state)
    states[str(chat_id)] = game_state.to_dict()
    await ParamService(session).set_parameter('race_state', json.dumps(states, ensure_ascii=False))


async def remove_state(chat_id: int, session):
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
        game_state = generate_game_with_weather_forecast()
        await save_state(message.chat.id, game_state, session)
        await AuditService(session).log_action(driver.id, UserActionType.GAME, current_day, 0,
                                               f'{driver.title} Начинает игру "Гонки"')
    content, builder, players = await get_game_message(game_state, session)
    content += HashTag("#гонки")
    await message.answer_photo(show_caption_above_media=False,
                               photo=await get_media(players),
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

    if len(game_state.player_ids) >= MAX_PLAYERS:
        await send_alarm(callback, "Состав заезда определен, начните заезд!")
        return

    if game_state.is_in_game(driver):
        await send_alarm(callback, "⚠️ Вы уже участник заезда!")
        return

    karma = driver.get_karma()
    if karma < FEE:
        await send_alarm(callback, "⚠️ Недостаточно кармы!")
        return

    driver.attributes["karma"] = karma - FEE
    await AuditService(session).log_action(driver.id, UserActionType.GAME_KARMA, current_day, -FEE,
                                           f"{driver.title} Будет участвовать в заезде и заплатил -{FEE} кармы")

    game_state.add_player(driver)
    await save_state(callback.message.chat.id, game_state, session)

    content, builder, players = await get_game_message(game_state, session)
    content += HashTag("#гонки")
    await callback.message.answer_photo(show_caption_above_media=False,
                                        photo=await get_media(players),
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

    if len(game_state.player_ids) < MIN_PLAYERS:
        await send_alarm(callback, "⚠️ Недостаточно гонщиков в заезде!")
        return

    await AuditService(session).log_action(driver.id, UserActionType.GAME, current_day, 0,
                                           f'{driver.title} Начинает заезд в игре "Гонки"')

    content, _, players = await get_game_message(game_state, session)
    winners = create_race_gif(game_state, players, chat_id=chat_id,
                              output_path=f"race_{chat_id}.gif", frame_count=400, duration=2)
    medals = {1: "🥇", 2: "🥈", 3: "🥉", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣", 10: "🔟"}
    count = len(game_state.player_ids)
    total = FEE * count
    for idx, player_idx in enumerate(winners):
        place = idx + 1
        player = players[player_idx]
        content += f"{medals.get(place, place)} .. "
        content += Spoiler(f"{player.title:…<20}")
        prize = total * PLACE_PERCENT.get(place, 0) // 100
        if place == len(winners) and prize < FEE:
            prize = FEE
        if prize != 0:
            player.attributes["karma"] = player.get_karma() + prize
            await AuditService(session).log_action(player.id, UserActionType.GAME_KARMA, current_day, prize,
                                                   f"{player.title} За {place} место в заезде получил {prize:+d} кармы")

        content += '\n'
    content += '\n'
    content += HashTag("#гонки")
    await callback.message.answer_animation(animation=FSInputFile(f"race_{chat_id}.mp4"), supports_streaming=True)
    await callback.message.answer(**content.as_kwargs())
    await remove_state(chat_id, session)


@router.callback_query(MyCallback.filter(F.action == "check_wheels"),
                       flags={"check_driver": True})
async def join_race_callback(callback: CallbackQuery, callback_data: MyCallback, session, driver: Driver, current_day):
    wheels = driver.attributes.get("wheels", 0)
    text = "дождевые шины (дают + к скорости во время дождя)" if wheels == 1 else "слики (лучшие на сухой трассе)" if wheels == 2 else "универсальные шины"
    await send_alarm(callback, f"🛞 Сейчас на машине установлены {text}")


@router.callback_query(MyCallback.filter(F.action == "set_wheels"),
                       flags={"check_driver": True})
async def set_wheels_callback(callback: CallbackQuery, callback_data: MyCallback, session, driver: Driver, current_day):
    wheels = callback_data.spot_id
    driver.attributes["wheels"] = wheels
    text = "Дождевые шины (дают + к скорости во время дождя)" if wheels == 1 else "Слики (лучшие на сухой трассе)" if wheels == 2 else "Универсальные шины"
    await send_alarm(callback, f"🛞 {text} успешно установлены")


async def get_media(players):
    if len(players) < MIN_PLAYERS:
        file = get_random_filename("./pics/racing")
        if file:
            return FSInputFile(os.path.join("./pics/racing", file))
        return FSInputFile("./pics/racing.jpg")
    track = draw_start_race_track(players, bg_color=(120, 120, 120), track_length=len(players) * 120)
    img_buffer = BytesIO()
    track.save(img_buffer, format="PNG")
    img_buffer.seek(0)
    return BufferedInputFile(img_buffer.getvalue(), filename="race.png")


def get_random_filename(directory_path):
    """
    Возвращает случайное имя файла из директории directory_path.
    Если директория пуста или не существует – возвращает None.
    """
    try:
        # Получаем список всех файлов и папок в директории
        entries = os.listdir(directory_path)
    except FileNotFoundError:
        # Директория не найдена
        print(f"Директория '{directory_path}' не существует.")
        return None
    except PermissionError:
        # Недостаточно прав для чтения директории
        print(f"Нет прав на чтение директории '{directory_path}'.")
        return None

    # Фильтруем только файлы (если нужны только файлы, а не подпапки)
    files = [f for f in entries if os.path.isfile(os.path.join(directory_path, f))]

    if not files:
        print("Директория пуста или в ней нет файлов.")
        return None

    # Выбираем случайный файл
    random_file = random.choice(files)
    return random_file


async def get_game_message(game_state: GameState, session):
    content = Bold(f"🏁 Игра «Гонки» 🏎️🚙🚗🚌🛻🚜\n\n")
    content += "Достаточно нажать «участвовать в заезде» и выбрать шины по погоде.\n"
    content += "Гонка проходит автоматически.\n\n"
    count = len(game_state.player_ids)
    total = FEE * count
    content += as_key_value("Количество участников", count)
    content += '\n'
    if count >= MIN_PLAYERS:
        content += Text("\nЗа 🥇 место выигрыш: ") + Code(f"{(total * PLACE_PERCENT.get(1, 0) // 100):+4d} 💟")
        content += Text("\nЗа 🥈 место выигрыш: ") + Code(f"{(total * PLACE_PERCENT.get(2, 0) // 100):+4d} 💟")
        content += Text("\nЗа 🥉 место выигрыш: ") + Code(f"{(total * PLACE_PERCENT.get(3, 0) // 100):+4d} 💟")
        content += Text("\nЗа 4️⃣ место выигрыш: ") + Code(f"{(total * PLACE_PERCENT.get(4, 0) // 100):+4d} 💟")
        content += Text("\nЗа 5️⃣ место выигрыш: ") + Code(f"{(total * PLACE_PERCENT.get(5, 0) // 100):+4d} 💟")
        content += Text("\nПриз за последнее место:  ") + Code(f"{FEE} 💟")
        content += '\n\n'
    players = []
    for idx, player_id in enumerate(game_state.player_ids):
        player = await DriverService(session).get_by_id(player_id)
        players.append(player)
        if count < MIN_PLAYERS:
            content += f"{idx + 1}. {player.title}\n"
    if count < MIN_PLAYERS:
        content += '\n'
    content += Bold("Прогноз погоды на заезд:\n")
    weather_forecast = game_state.weather

    part1 = weather_forecast.get('1')
    part2 = weather_forecast.get('2')
    content += f"Участок 1:    {part1[2] * 10}% ☀️,  {part1[1] * 10}% 🌧️\n"
    content += f"Участок 2:    {part2[2] * 10}% ☀️,  {part2[1] * 10}% 🌧️\n"
    content += f"Участок 3: Погода будет такой, под которую выбрано меньше всего шин\n"
    content += '\n'
    builder = await get_race_keyboard(game_state)
    return content, builder, players


async def get_race_keyboard(game_state: GameState):
    builder = InlineKeyboardBuilder()
    keyboard_sizes = []
    players_count = len(game_state.player_ids)
    if players_count < MAX_PLAYERS:
        add_button(f"Участвовать (плата 💟 {FEE} кармы)", "join_race", 0, builder)
        keyboard_sizes.append(1)

    add_button(f"ℹ️ Проверить колеса 🛞🛞🛞🛞", "check_wheels", 0, builder)
    keyboard_sizes.append(1)
    add_button(f"🛞 для ☀️", "set_wheels", 0, builder, spot_id=2)
    add_button(f"🛞 для ☁️", "set_wheels", 0, builder, spot_id=0)
    add_button(f"🛞 для 🌧️", "set_wheels", 0, builder, spot_id=1)
    keyboard_sizes.append(3)
    # if players_count >= 30:
    #     add_button("😇 Помочь сопернику", "race_help_opponent", 0, builder)
    #     for i in range(1, players_count + 1):
    #         add_button(f"😇 {i}", "race_help_opponent", 0, builder, spot_id=i)
    #     add_button("😈 Сделать пакость", "race_joke_opponent", 0, builder)
    #     for i in range(1, players_count + 1):
    #         add_button(f"😈 {i}", "race_joke_opponent", 0, builder, spot_id=i)
    #     if players_count > 6:
    #         keyboard_sizes.append(1)
    #         keyboard_sizes.append(int(players_count / 2))
    #         keyboard_sizes.append(players_count - int(players_count / 2))
    #         keyboard_sizes.append(1)
    #         keyboard_sizes.append(int(players_count / 2))
    #         keyboard_sizes.append(players_count - int(players_count / 2))
    #     else:
    #         keyboard_sizes.append(1)
    #         keyboard_sizes.append(players_count)
    #         keyboard_sizes.append(1)
    #         keyboard_sizes.append(players_count)

    if players_count >= MIN_PLAYERS:
        add_button("🏁 Начать гонку!", "start_race", 0, builder)
        keyboard_sizes.append(1)
    builder.adjust(*keyboard_sizes)
    return builder
