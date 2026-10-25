import json
import logging
import os
import random
from datetime import datetime
from io import BytesIO

from aiogram import Router, F
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import (
    CallbackQuery, Message, FSInputFile, BufferedInputFile, User,
    DisabledButton,
    InputRichBlockButtons, InputRichBlockParagraph, InputRichBlockSectionHeading,
    InputRichBlockTable, InputRichMessage, RichBlockTableCell,
    RichMessageButton, RichTextButton, RichTextTextMention,
)
from aiogram.utils.formatting import Bold, Spoiler, as_key_value, Code, Text, HashTag, TextMention
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from handlers.driver_callback import add_button, MyCallback
from models.driver import Driver
from models.user_audit import UserActionType
from services.audit_service import AuditService
from services.driver_service import DriverService
from services.notification_sender import send_alarm
from services.param_service import ParamService
from services.telegram_ui import answer_rich, edit_rich
from utils.cars_generator import draw_start_race_track, create_race_gif
from utils.game_race_utils import GameState, generate_game_with_weather_forecast
from utils.race_simulation import (
    NITRO_RULES_VERSION, RACE_ENTRY_FEE, RaceAction, allocate_prizes,
    initial_nitro, resolve_race_simulation,
)

MIN_PLAYERS = 7
MAX_PLAYERS = 12
FEE = RACE_ENTRY_FEE

router = Router()
logger = logging.getLogger(__name__)
_race_scheduler = None


def register_race_scheduler(scheduler):
    """Подключить планировщик автоматического старта по дедлайну."""
    global _race_scheduler
    _race_scheduler = scheduler


def _deadline_job_id(chat_id: int):
    """Сформировать уникальный идентификатор задачи для чата."""
    return f"race-deadline-{chat_id}"


def _schedule_deadline(bot, chat_id: int, game_state: GameState):
    """Создать или обновить задачу завершения окна выбора."""
    if _race_scheduler is None or game_state.phase != "selection":
        return
    deadline = datetime.fromisoformat(game_state.selection_deadline)
    _race_scheduler.add_job(
        process_race_deadline,
        "date", run_date=deadline,
        args=(bot, chat_id),
        id=_deadline_job_id(chat_id), replace_existing=True,
        misfire_grace_time=None,
    )


def _unschedule_deadline(chat_id: int):
    """Удалить задачу после досрочного или обычного старта."""
    if _race_scheduler and _race_scheduler.get_job(_deadline_job_id(chat_id)):
        _race_scheduler.remove_job(_deadline_job_id(chat_id))


async def restore_race_deadlines(bot, session):
    """Восстановить таймеры и перевести открытые старые гонки на новые правила."""
    raw = await ParamService(session).get_parameter("race_state", "{}")
    states = json.loads(raw)
    if not isinstance(states, dict):
        logger.warning("Некорректный формат race_state: ожидался JSON-объект")
        return

    migrated = []
    for chat_id, data in states.items():
        # Запись может быть пустой после завершения гонки или сохранена в
        # формате предыдущей версии игры. Такие записи не являются активными
        # выборами и не должны мешать запуску бота.
        if not isinstance(data, dict) or data.get("phase") != "selection":
            continue
        try:
            state = GameState.from_dict(data)
            if state.migrate_legacy_selection(datetime.now()):
                states[chat_id] = state.to_dict()
                migrated.append(chat_id)
            _schedule_deadline(bot, int(chat_id), state)
        except (KeyError, TypeError, ValueError):
            logger.warning(
                "Пропуск некорректного race_state для чата %s",
                chat_id,
                exc_info=True,
            )
    if migrated:
        await ParamService(session).set_parameter(
            "race_state", json.dumps(states, ensure_ascii=False),
        )
        await session.commit()
        for chat_id in migrated:
            try:
                await bot.send_message(
                    chat_id=int(chat_id),
                    text="🏁 Правила гонки обновились. Старые карты сброшены, "
                         "шины сохранены. У вас новый час, чтобы выбрать перевозки "
                         "нитро, защиту и план гонки.",
                )
            except TelegramAPIError:
                logger.warning("Не удалось уведомить чат %s о новых правилах", chat_id)


async def get_state(chat_id: int, session) -> GameState | None:
    """Загрузить состояние гонки чата, отвергая некорректный старый выбор."""
    race_state = await ParamService(session).get_parameter('race_state', '{}')
    states = json.loads(race_state)
    state_dict = states.get(str(chat_id), None)
    if not isinstance(state_dict, dict) or "phase" not in state_dict:
        return None
    try:
        state = GameState.from_dict(state_dict)
        if state.phase == "selection" and state.rules_version != NITRO_RULES_VERSION:
            # При запуске такое состояние обычно мигрирует. Не смешиваем
            # старые карты с расчётом нитро, если миграция не состоялась.
            logger.warning("Гонка %s ожидает миграции правил при запуске", chat_id)
            return None
        return state
    except (KeyError, TypeError, ValueError):
        logger.warning(
            "Некорректный race_state для чата %s; считаем игру неактивной",
            chat_id,
            exc_info=True,
        )
        return None


async def save_state(chat_id: int, game_state: GameState, session):
    """Сохранить состояние одной гонки среди состояний всех чатов."""
    race_state = await ParamService(session).get_parameter('race_state', '{}')
    states = json.loads(race_state)
    states[str(chat_id)] = game_state.to_dict()
    await ParamService(session).set_parameter('race_state', json.dumps(states, ensure_ascii=False))


async def remove_state(chat_id: int, session):
    """Убрать завершённую гонку из хранилища состояний."""
    race_state = await ParamService(session).get_parameter('race_state', '{}')
    states = json.loads(race_state)
    states[str(chat_id)] = None
    await ParamService(session).set_parameter('race_state', json.dumps(states))


def _callback(action: str, user_id: int, *, spot_id=None, event_type=None,
              bool_value=None, chat_id=None):
    """Упаковать действие кнопки вместе с водителем и исходным чатом."""
    return MyCallback(
        action=action, user_id=user_id, spot_id=spot_id, day_num=chat_id,
        event_type=event_type, bool_value=bool_value,
    ).pack()


def _table_cell(text, *, header=False, align="left"):
    """Собрать ячейку компактной таблицы Telegram."""
    return RichBlockTableCell(
        text=text, align="center" if header else align, valign="middle",
        is_header=True if header else None,
    )


def _driver_mention(driver: Driver, *, compact=False):
    """Создать упоминание водителя, при необходимости сократив подпись."""
    title = driver.title
    if compact and len(title) > 12:
        title = f"{title[:11]}…"
    return RichTextTextMention(
        text=title,
        user=User(id=driver.chat_id, is_bot=False, first_name=driver.title),
    )


def _wheel_icon(wheels):
    """Вернуть значок выбранного типа шин."""
    return {0: "🛞", 1: "🌧️", 2: "☀️"}.get(wheels, "—")


def _deadline_text(game_state: GameState):
    """Показать время закрытия выбора в коротком формате."""
    if not game_state.selection_deadline:
        return "окно выбора не открыто"
    deadline = datetime.fromisoformat(game_state.selection_deadline)
    return deadline.strftime("%H:%M")


def _selection_open(game_state: GameState | None) -> bool:
    """Проверить, можно ли ещё менять личное решение."""
    return (
            game_state is not None and game_state.phase == "selection"
            and not game_state.deadline_reached(datetime.now())
    )


def _race_chat_id(callback: CallbackQuery, callback_data: MyCallback | None = None) -> int:
    """Найти групповой чат гонки даже из личной панели водителя."""
    return (
        callback_data.day_num
        if callback_data is not None and callback_data.day_num is not None
        else callback.message.chat.id
    )


def _public_race_message(game_state: GameState, players, *, admin_ready=False):
    """Показать только состав и подтверждения, не раскрывая тайный выбор."""
    mentions = []
    for index, player in enumerate(players):
        if index:
            mentions.append(" · ")
        mentions.append(_driver_mention(player))

    rows = [[
        _table_cell("👤", header=True),
        _table_cell("✓", header=True),
    ]]
    for player in players:
        rows.append([
            _table_cell(_driver_mention(player, compact=True)),
            _table_cell("✅" if player.id in game_state.confirmed else "…", align="center"),
        ])

    blocks = [
        InputRichBlockSectionHeading(text="🏁 Гонка: нитро и интриги", size=1),
        InputRichBlockParagraph(text=[
            "Участники: ", *mentions,
            f"\n⏱ Тайный выбор до {_deadline_text(game_state)}.",
            "\nНажмите «🎮 Мой выбор», чтобы открыть личную панель.",
        ]),
        InputRichBlockTable(
            cells=rows, is_bordered=True, is_striped=True, is_compact=True,
        ),
    ]
    buttons = [
        RichMessageButton(
            text="🎮 Мой выбор",
            callback_data=_callback("race_panel", 0),
        ),
        RichMessageButton(
            text="🔄 Обновить",
            callback_data=_callback("race_refresh", 0),
        ),
    ]
    if admin_ready:
        buttons.append(RichMessageButton(
            text="🏁 Начать заезд сейчас",
            callback_data=_callback("race_start_now", 0),
        ))
    blocks.append(InputRichBlockButtons(buttons=buttons, align="center"))
    return InputRichMessage(blocks=blocks)


def _panel_message(game_state: GameState, driver: Driver, players, chat_id=None,
                   picker=None):
    """Собрать личную панель шин, перевозок, защиты и плана гонки."""
    wheel = game_state.wheels.get(str(driver.id), game_state.wheels.get(driver.id))
    action = game_state.actions.get(driver.id, RaceAction(kind="nitro"))
    names = {player.id: player.title[:12] for player in players}
    count = game_state.target_count()

    wheel_rows = [[
        _table_cell("Шины", header=True), _table_cell("Выбор", header=True),
    ]]
    for wheel_id, label in (
            (0, "🛞 Универсальные"), (1, "🌧️ Дождевые"), (2, "☀️ Слики"),
    ):
        wheel_rows.append([
            _table_cell(label),
            _table_cell(RichTextButton(button=RichMessageButton(
                text="✅" if wheel == wheel_id else "Выбрать",
                callback_data=_callback("race_wheel", driver.chat_id,
                                        spot_id=wheel_id, chat_id=chat_id),
            )), align="center"),
        ])

    transfer_rows = [[_table_cell("#", header=True),
                      _table_cell("Забрать у", header=True),
                      _table_cell("Передать", header=True)]]
    for slot in range(count):
        source, recipient = (action.transfers[slot] if slot < len(action.transfers)
                             else (-1, -1))
        transfer_rows.append([
            _table_cell(str(slot + 1)),
            *(_table_cell(RichTextButton(button=RichMessageButton(
                text=names.get(target, "Выбрать"),
                callback_data=_callback("race_pick", driver.chat_id,
                                        event_type=f"{role}{slot}", chat_id=chat_id),
            )), align="center")
                for target, role in ((source, "s"), (recipient, "r"))),
        ])
    plans = (("early", "🚀 Рывок"), ("steady", "⚖️ Ровно"),
             ("late", "🏁 Финиш"))
    plan_rows = [[_table_cell("План", header=True),
                  _table_cell("Выбор", header=True)]]
    for key, title in plans:
        plan_rows.append([
            _table_cell(title),
            _table_cell(RichTextButton(button=RichMessageButton(
                text="✅" if action.kind == "nitro" and action.plan == key else "Выбрать",
                callback_data=_callback("race_plan", driver.chat_id,
                                        event_type=key, chat_id=chat_id),
            )), align="center"),
        ])
    blocks = [
        InputRichBlockSectionHeading(text="🎮 Ваш выбор", size=1),
        InputRichBlockParagraph(text=(
            f"{driver.title}: шины {_wheel_icon(wheel)}. "
            f"Начальный запас: {initial_nitro(len(players))} нитро."
        )),
        InputRichBlockTable(
            cells=wheel_rows, is_bordered=True, is_striped=True, is_compact=True,
        ),
        InputRichBlockTable(
            cells=transfer_rows, is_bordered=True, is_striped=True, is_compact=True,
        ),
        InputRichBlockParagraph(
            text="Каждая строка переносит 1 нитро. Если кражу заблокировали, "
                 "отдаёте своё; если подарок заблокировали, нитро остаётся вам."
        ),
    ]
    guard_rows = [[_table_cell("Защита от", header=True),
                   _table_cell("Выбор", header=True)]]
    for target in players:
        if target.id == driver.id:
            continue
        guard_rows.append([
            _table_cell(target.title[:12]),
            _table_cell(RichTextButton(button=RichMessageButton(
                text="🛡️" if target.id in action.guards else "—",
                callback_data=_callback("race_guard", driver.chat_id,
                                        spot_id=target.id, chat_id=chat_id),
            )), align="center"),
        ])
    blocks.append(InputRichBlockParagraph(
        text=f"Защита от {len(action.guards)}/{count} игроков:"
    ))
    blocks.append(InputRichBlockTable(
        cells=guard_rows, is_bordered=True, is_striped=True, is_compact=True,
    ))
    blocks.append(InputRichBlockTable(
        cells=plan_rows, is_bordered=True, is_striped=True, is_compact=True,
    ))
    if picker:
        role, slot = picker[0], int(picker[1:])
        target_rows = [[_table_cell(
            f"№{slot + 1}: {'забрать у' if role == 's' else 'передать'}",
            header=True)]]
        for target in players:
            if target.id == driver.id:
                continue
            target_rows.append([_table_cell(RichTextButton(button=RichMessageButton(
                text=target.title[:16],
                callback_data=_callback("race_target", driver.chat_id,
                                        spot_id=target.id, event_type=picker,
                                        chat_id=chat_id),
            )))])
        blocks.append(InputRichBlockTable(
            cells=target_rows, is_bordered=True, is_striped=True, is_compact=True,
        ))

    ready = game_state.ready(driver.id)
    confirmed = driver.id in game_state.confirmed
    blocks.append(InputRichBlockButtons(buttons=[RichMessageButton(
        text="✅ Выбор сохранён" if confirmed else (
            "✅ Сохранить выбор" if ready else "⏳ Выбор не завершён"
        ),
        callback_data=_callback("race_confirm", driver.chat_id,
                                chat_id=chat_id) if ready else None,
        disabled=None if ready else DisabledButton(),
    )], align="center"))
    return InputRichMessage(blocks=blocks)


def _panel_fallback(game_state: GameState, driver: Driver) -> str:
    """Подготовить текст личной панели, если rich-интерфейс недоступен."""
    wheel = game_state.wheels.get(str(driver.id), "—")
    action = game_state.actions.get(driver.id, RaceAction(kind="nitro"))
    return (
        f"🎮 Ваш выбор\nШины: {_wheel_icon(wheel)}\n"
        f"План: {action.plan}\n"
        f"Перевозок: {sum(-1 not in pair for pair in action.transfers)}"
        f"/{game_state.target_count()}, защит: {len(action.guards)}.\n"
        "Кнопки: шины, пары «забрать → передать», защита, план."
    )


def _panel_keyboard(game_state: GameState, driver: Driver, players, chat_id=None,
                    picker=None):
    """Собрать обычные кнопки выбора, включая открытый список целей."""
    builder = InlineKeyboardBuilder()
    for wheel_id, icon in ((0, "🛞"), (1, "🌧️"), (2, "☀️")):
        builder.button(text=icon, callback_data=_callback(
            "race_wheel", driver.chat_id, spot_id=wheel_id, chat_id=chat_id,
        ))
    action = game_state.actions.get(driver.id, RaceAction(kind="nitro"))
    names = {player.id: player.title[:10] for player in players}
    for slot in range(game_state.target_count()):
        source, recipient = (action.transfers[slot] if slot < len(action.transfers)
                             else (-1, -1))
        for role, target, icon in (("s", source, "⛽"), ("r", recipient, "🎁")):
            builder.button(
                text=f"{slot + 1}{icon} {names.get(target, 'выбрать')}",
                callback_data=_callback("race_pick", driver.chat_id,
                                        event_type=f"{role}{slot}", chat_id=chat_id),
            )
    for player in players:
        if player.id != driver.id:
            builder.button(
                text=f"{'🛡️' if player.id in action.guards else '○'} {player.title[:10]}",
                callback_data=_callback("race_guard", driver.chat_id,
                                        spot_id=player.id, chat_id=chat_id),
            )
    for plan, label in (("early", "🚀"), ("steady", "⚖️"), ("late", "🏁")):
        builder.button(text=f"{label}{'✓' if action.plan == plan else ''}",
                       callback_data=_callback("race_plan", driver.chat_id,
                                               event_type=plan, chat_id=chat_id))
    if picker:
        for player in players:
            if player.id != driver.id:
                builder.button(
                    text=f"➡️ {player.title[:12]}",
                    callback_data=_callback("race_target", driver.chat_id,
                                            spot_id=player.id, event_type=picker,
                                            chat_id=chat_id),
                )
    builder.button(
        text="✅ Готово",
        callback_data=_callback("race_confirm", driver.chat_id, chat_id=chat_id),
    )
    builder.adjust(3, *([2] * game_state.target_count()), *([2] * (len(players) - 1)),
                   3, *([2] * (len(players) - 1) if picker else []), 1)
    return builder.as_markup()


def _public_fallback_keyboard(game_state: GameState):
    """Собрать кнопки общего сообщения без личных данных игроков."""
    builder = InlineKeyboardBuilder()
    add_button("🎮 Мой выбор", "race_panel", 0, builder)
    add_button("🔄 Обновить", "race_refresh", 0, builder)
    if game_state.all_ready():
        add_button("🏁 Начать заезд сейчас", "race_start_now", 0, builder)
    builder.adjust(1)
    return builder.as_markup()


def _result_rich_message(simulation, players, game_state: GameState):
    """Показать места и награды без журнала краж и подарков."""
    rows = [[
        _table_cell("🏁", header=True),
        _table_cell("👤", header=True),
        _table_cell("🛞", header=True),
        _table_cell("⚡", header=True),
        _table_cell("💟", header=True),
    ]]
    for place, player_idx in enumerate(simulation.winners, start=1):
        player = players[player_idx]
        rows.append([
            _table_cell(str(place), align="center"),
            _table_cell(_driver_mention(player, compact=True)),
            _table_cell(_wheel_icon(simulation.wheels[player_idx]), align="center"),
            _table_cell(str(simulation.nitro[player_idx]), align="center"),
            _table_cell(f"+{simulation.prizes.get(place, 0)}", align="center"),
        ])

    weather_icons = ("☁️", "🌧️", "☀️")
    blocks = [
        InputRichBlockSectionHeading(text="🏁 Результаты гонки", size=1),
        InputRichBlockParagraph(text=(
                "Погода: " + " · ".join(
            weather_icons[weather] for weather in simulation.weather_segments
        )
        )),
        InputRichBlockTable(
            cells=rows, is_bordered=True, is_striped=True, is_compact=True,
        ),
    ]
    return InputRichMessage(blocks=blocks)


def _nitro_rich_message(simulation, players):
    """Показать итоговые запасы нитро сразу после закрытия выбора."""
    rows = [[_table_cell("👤", header=True), _table_cell("Нитро", header=True)]]
    for index, player in enumerate(players):
        rows.append([
            _table_cell(_driver_mention(player, compact=True)),
            _table_cell(str(simulation.nitro[index]), align="center"),
        ])
    return InputRichMessage(blocks=[
        InputRichBlockSectionHeading(text="⚡ Нитро перед стартом", size=1),
        InputRichBlockParagraph(
            text="Выбор закрыт. Показаны только итоговые запасы; "
                 "перевозки, защита и планы соперников не раскрываются."
        ),
        InputRichBlockTable(cells=rows, is_bordered=True, is_striped=True,
                            is_compact=True),
    ])


async def _update_public_race_message(bot, chat_id: int, game_state: GameState, players):
    """Обновить общий статус подтверждений с текстовым запасным вариантом."""
    if not game_state.public_message_id:
        return
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=game_state.public_message_id,
            rich_message=_public_race_message(
                game_state, players, admin_ready=game_state.all_ready(),
            ),
        )
    except TelegramBadRequest as error:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=game_state.public_message_id,
                text=(
                    f"🏁 Гонка. Подтвердили выбор: "
                    f"{len(game_state.confirmed)}/{len(players)}. "
                    f"Окончание: {_deadline_text(game_state)}."
                ),
                reply_markup=_public_fallback_keyboard(game_state),
            )
        except Exception:
            logger.warning("Не удалось обновить сообщение гонки: %s", error)


async def _send_selection_window(callback: CallbackQuery, game_state: GameState, session):
    """Опубликовать окно выбора перед удалением старого сообщения набора."""
    chat_id = callback.message.chat.id
    players = [
        await DriverService(session).get_by_id(player_id)
        for player_id in game_state.player_ids
    ]
    fallback = Text(
        f"🏁 Окно выбора открыто до {_deadline_text(game_state)}.\n",
        *(
            TextMention(
                f"{player.title} ",
                user=User(
                    id=player.chat_id, is_bot=False, first_name=player.title,
                ),
            )
            for player in players
        ),
    )
    fallback_markup = _public_fallback_keyboard(game_state)
    try:
        sent = await callback.message.bot.send_rich_message(
            chat_id=chat_id,
            rich_message=_public_race_message(game_state, players),
        )
    except TelegramAPIError:
        logger.warning(
            "Rich-сообщение окна выбора не отправлено в чат %s; "
            "пробуем обычное сообщение",
            chat_id, exc_info=True,
        )
        sent = None
    # Не удаляем рабочее сообщение набора, пока новое сообщение не создано.
    # Если rich API или его fallback недоступны, участники должны хотя бы
    # сохранить старое сообщение и возможность повторить действие.
    if sent is None:
        try:
            sent = await callback.message.bot.send_message(
                chat_id=chat_id,
                **fallback.as_kwargs(),
                reply_markup=fallback_markup,
            )
        except TelegramAPIError:
            logger.exception("Не удалось отправить окно выбора гонки в чат %s", chat_id)
            return None
    if sent is None:
        logger.error("Telegram вернул пустой ответ при отправке окна выбора в чат %s", chat_id)
        return None
    game_state.public_message_id = sent.message_id
    await save_state(chat_id, game_state, session)
    try:
        await callback.message.delete()
    except Exception:
        logger.warning(
            "Не удалось удалить старое сообщение набора гонки в чате %s",
            chat_id,
            exc_info=True,
        )
    return sent


@router.message(
    F.text.regexp(r"(?i).*((да начнется гонка)|(инфо гонка))"),
    flags={"lock_operation": "race", "long_operation": "upload_photo", "check_admin": True, "check_driver": True})
async def game_race(message: Message, session: AsyncSession, driver: Driver, current_day, is_private):
    """Создать лобби или показать актуальное состояние гонки в группе."""
    if is_private:
        await message.answer("Команда недоступна в личных сообщениях.")
        return

    game_state = await get_state(message.chat.id, session)
    if game_state is None:
        game_state = generate_game_with_weather_forecast()
        await save_state(message.chat.id, game_state, session)
        await AuditService(session).log_action(driver.id, UserActionType.GAME, current_day, 0,
                                               f'{driver.title} Начинает игру "Гонки"')
    if game_state.phase == "running":
        await message.answer("🏁 Заезд уже идёт. Результат появится после финиша.")
        return
    if game_state.phase == "selection":
        players = [
            await DriverService(session).get_by_id(player_id)
            for player_id in game_state.player_ids
        ]
        await answer_rich(
            message,
            _public_race_message(game_state, players, admin_ready=game_state.all_ready()),
            fallback_text=f"🏁 Окно выбора открыто до {_deadline_text(game_state)}.",
            fallback_reply_markup=_public_fallback_keyboard(game_state),
        )
        return
    content, builder, players = await get_game_message(game_state, session)
    content += HashTag("#гонки")
    sent = await message.answer_photo(
        show_caption_above_media=False, photo=await get_media(players),
        reply_markup=builder.as_markup(),
        **content.as_kwargs(text_key="caption", entities_key="caption_entities"),
    )
    game_state.public_message_id = sent.message_id
    await save_state(message.chat.id, game_state, session)


@router.callback_query(MyCallback.filter(F.action == "join_race"),
                       flags={"lock_operation": "race",
                              "long_operation": "upload_photo",
                              "check_driver": True})
async def join_race_callback(callback: CallbackQuery, callback_data: MyCallback, session, driver: Driver, current_day):
    """Списать взнос и добавить водителя в ещё открытый набор."""
    game_state = await get_state(callback.message.chat.id, session)
    if game_state is None:
        await send_alarm(callback, "⚠️ Начните Новую игру!")
        return

    if game_state.phase != "lobby":
        await send_alarm(callback, "⚠️ Набор в этот заезд уже закрыт.")
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
    sent = await callback.message.answer_photo(
        show_caption_above_media=False, photo=await get_media(players),
        reply_markup=builder.as_markup(),
        **content.as_kwargs(text_key="caption", entities_key="caption_entities"),
    )
    game_state.public_message_id = sent.message_id
    await save_state(callback.message.chat.id, game_state, session)
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
    """Закрыть набор, открыть часовой выбор и запланировать старт."""
    chat_id = callback.message.chat.id
    game_state = await get_state(chat_id, session)
    if game_state is None:
        await send_alarm(callback, "⚠️ Начните Новую игру!")
        return

    if game_state.phase != "lobby":
        await send_alarm(callback, "⚠️ Окно выбора уже открыто или заезд завершён.")
        return

    if len(game_state.player_ids) < MIN_PLAYERS:
        await send_alarm(callback, "⚠️ Недостаточно гонщиков в заезде!")
        return

    game_state.begin_selection(datetime.now(), random.randrange(2 ** 31))
    sent = await _send_selection_window(callback, game_state, session)
    if sent is None:
        # Старое сообщение набора не удалено и состояние в БД осталось lobby.
        await send_alarm(callback, "⚠️ Не удалось открыть окно выбора. Попробуйте снова.")
        return
    await AuditService(session).log_action(driver.id, UserActionType.GAME, current_day, 0,
                                           f'{driver.title} Открывает окно выбора в игре "Гонки"')
    _schedule_deadline(callback.message.bot, chat_id, game_state)
    await callback.answer("Окно выбора открыто на 1 час")


async def _show_race_panel(callback, game_state: GameState, driver: Driver, session,
                           chat_id: int, picker=None):
    """Показать или обновить личную панель только этому водителю."""
    players = [
        await DriverService(session).get_by_id(player_id)
        for player_id in game_state.player_ids
    ]
    rich = _panel_message(game_state, driver, players, chat_id, picker)
    fallback = _panel_fallback(game_state, driver)
    keyboard = _panel_keyboard(game_state, driver, players, chat_id, picker)
    if (getattr(callback.message, "ephemeral_message_id", None)
            or callback.message.chat.type == "private"):
        await edit_rich(
            callback, rich, personal=True, fallback_text=fallback,
            fallback_reply_markup=keyboard,
        )
    else:
        await answer_rich(
            callback, rich, personal=True, fallback_text=fallback,
            fallback_reply_markup=keyboard,
        )


async def _refresh_public_status(bot, chat_id, game_state, session):
    """Перечитать участников и обновить общий счётчик подтверждений."""
    players = [
        await DriverService(session).get_by_id(player_id)
        for player_id in game_state.player_ids
    ]
    await _update_public_race_message(bot, chat_id, game_state, players)


@router.callback_query(MyCallback.filter(F.action == "race_panel"),
                       flags={"check_driver": True})
async def race_panel_callback(callback: CallbackQuery, callback_data: MyCallback,
                              session, driver: Driver):
    """Открыть личную панель зарегистрированного участника."""
    chat_id = _race_chat_id(callback, callback_data)
    game_state = await get_state(chat_id, session)
    if not _selection_open(game_state) or driver.id not in game_state.player_ids:
        await send_alarm(callback, "⚠️ Окно выбора закрыто.")
        return
    await _show_race_panel(callback, game_state, driver, session, chat_id)
    await callback.answer()


@router.callback_query(MyCallback.filter(F.action == "race_refresh"),
                       flags={"check_driver": True})
async def race_refresh_callback(callback: CallbackQuery, callback_data: MyCallback,
                                session, driver: Driver):
    """Обновить общее сообщение по запросу из чата."""
    chat_id = _race_chat_id(callback, callback_data)
    game_state = await get_state(chat_id, session)
    if game_state is None:
        await send_alarm(callback, "⚠️ Заезд не найден.")
        return
    await _refresh_public_status(callback.message.bot, chat_id, game_state, session)
    await callback.answer("Статус обновлён")


@router.callback_query(MyCallback.filter(F.action == "race_wheel"),
                       flags={"check_driver": True, "check_callback": True,
                              "lock_operation": "race"})
async def race_wheel_callback(callback: CallbackQuery, callback_data: MyCallback,
                              session, driver: Driver):
    """Сохранить выбранные шины и снять старое подтверждение."""
    chat_id = _race_chat_id(callback, callback_data)
    game_state = await get_state(chat_id, session)
    if not _selection_open(game_state):
        await send_alarm(callback, "⚠️ Окно выбора закрыто.")
        return
    try:
        game_state.set_wheels(driver, int(callback_data.spot_id))
    except ValueError as error:
        await send_alarm(callback, f"⚠️ {error}")
        return
    await save_state(chat_id, game_state, session)
    await callback.answer("Шины выбраны")
    await _show_race_panel(callback, game_state, driver, session, chat_id)
    await _refresh_public_status(callback.message.bot, chat_id, game_state, session)


@router.callback_query(MyCallback.filter(F.action == "race_plan"),
                       flags={"check_driver": True, "check_callback": True,
                              "lock_operation": "race"})
async def race_plan_callback(callback: CallbackQuery, callback_data: MyCallback,
                             session, driver: Driver):
    """Сохранить тайный план расхода нитро."""
    chat_id = _race_chat_id(callback, callback_data)
    game_state = await get_state(chat_id, session)
    if not _selection_open(game_state):
        await send_alarm(callback, "⚠️ Окно выбора закрыто.")
        return
    try:
        game_state.choose_plan(driver.id, callback_data.event_type)
    except ValueError as error:
        await send_alarm(callback, f"⚠️ {error}")
        return
    await save_state(chat_id, game_state, session)
    await callback.answer("План выбран")
    await _show_race_panel(callback, game_state, driver, session, chat_id)
    await _refresh_public_status(callback.message.bot, chat_id, game_state, session)


def _parse_picker(picker, count):
    """Проверить код стороны и номера пары из кнопки выбора цели."""
    if (not isinstance(picker, str) or len(picker) != 2
            or picker[0] not in ("s", "r") or not picker[1].isdigit()
            or int(picker[1]) >= count):
        raise ValueError("Invalid transfer slot")
    return picker[0], int(picker[1])


@router.callback_query(MyCallback.filter(F.action == "race_pick"),
                       flags={"check_driver": True, "check_callback": True,
                              "lock_operation": "race"})
async def race_pick_callback(callback: CallbackQuery, callback_data: MyCallback,
                             session, driver: Driver):
    """Открыть список водителей для одной стороны пары перевозки."""
    chat_id = _race_chat_id(callback, callback_data)
    game_state = await get_state(chat_id, session)
    if not _selection_open(game_state) or driver.id not in game_state.player_ids:
        await send_alarm(callback, "⚠️ Окно выбора закрыто.")
        return
    try:
        _parse_picker(callback_data.event_type, game_state.target_count())
    except ValueError as error:
        await send_alarm(callback, f"⚠️ {error}")
        return
    await _show_race_panel(callback, game_state, driver, session, chat_id,
                           callback_data.event_type)
    await callback.answer()


@router.callback_query(MyCallback.filter(F.action == "race_guard"),
                       flags={"check_driver": True, "check_callback": True,
                              "lock_operation": "race"})
async def race_guard_callback(callback: CallbackQuery, callback_data: MyCallback,
                              session, driver: Driver):
    """Переключить защиту от конкретного соперника."""
    chat_id = _race_chat_id(callback, callback_data)
    game_state = await get_state(chat_id, session)
    if not _selection_open(game_state):
        await send_alarm(callback, "⚠️ Окно выбора закрыто.")
        return
    try:
        game_state.toggle_guard(driver.id, int(callback_data.spot_id))
    except ValueError as error:
        await send_alarm(callback, f"⚠️ {error}")
        return
    await save_state(chat_id, game_state, session)
    await callback.answer("Защита обновлена")
    await _show_race_panel(callback, game_state, driver, session, chat_id)
    await _refresh_public_status(callback.message.bot, chat_id, game_state, session)


@router.callback_query(MyCallback.filter(F.action == "race_target"),
                       flags={"check_driver": True, "check_callback": True,
                              "lock_operation": "race"})
async def race_target_callback(callback: CallbackQuery, callback_data: MyCallback,
                               session, driver: Driver):
    """Записать источник или получателя выбранной перевозки."""
    chat_id = _race_chat_id(callback, callback_data)
    game_state = await get_state(chat_id, session)
    if not _selection_open(game_state):
        await send_alarm(callback, "⚠️ Окно выбора закрыто.")
        return
    try:
        role, slot = _parse_picker(callback_data.event_type,
                                   game_state.target_count())
        game_state.set_transfer(
            driver.id, slot, "source" if role == "s" else "recipient",
            int(callback_data.spot_id),
        )
    except ValueError as error:
        await send_alarm(callback, f"⚠️ {error}")
        return
    await save_state(chat_id, game_state, session)
    await callback.answer("Перевозка обновлена")
    await _show_race_panel(callback, game_state, driver, session, chat_id)
    await _refresh_public_status(callback.message.bot, chat_id, game_state, session)


@router.callback_query(MyCallback.filter(F.action == "race_confirm"),
                       flags={"check_driver": True, "check_callback": True,
                              "lock_operation": "race"})
async def race_confirm_callback(callback: CallbackQuery, callback_data: MyCallback,
                                session, driver: Driver):
    """Подтвердить полный личный выбор для досрочного старта."""
    chat_id = _race_chat_id(callback, callback_data)
    game_state = await get_state(chat_id, session)
    if not _selection_open(game_state):
        await send_alarm(callback, "⚠️ Окно выбора закрыто.")
        return
    if not game_state.ready(driver.id):
        await send_alarm(callback, "⚠️ Выберите шины и заполните все перевозки.")
        return
    game_state.confirm(driver.id)
    await save_state(chat_id, game_state, session)
    await callback.answer("Выбор сохранён")
    await _show_race_panel(callback, game_state, driver, session, chat_id)
    await _refresh_public_status(callback.message.bot, chat_id, game_state, session)


async def execute_race(bot, chat_id: int, session, current_day=None):
    """Закрыть выбор, показать запасы, отрисовать заезд и выдать награды."""
    game_state = await get_state(chat_id, session)
    if game_state is None or game_state.phase != "selection":
        return False

    timed_out = not game_state.all_ready()
    if timed_out:
        game_state.fill_missing_choices()
    if not game_state.all_ready() and not timed_out:
        return False

    players = [
        await DriverService(session).get_by_id(player_id)
        for player_id in game_state.player_ids
    ]
    wheels = [
        int(game_state.wheels.get(str(player.id), game_state.wheels.get(player.id, 0)))
        for player in players
    ]
    simulation = resolve_race_simulation(
        players=players,
        wheels=wheels,
        weather_forecast=game_state.weather,
        actions=game_state.resolve_actions(),
        seed=(game_state.race_seed if game_state.race_seed is not None
              else random.randrange(2 ** 31)),
        frame_count=400,
        track_distance=1700,
        car_width=100,
    )
    game_state.phase = "running"
    await save_state(chat_id, game_state, session)
    try:
        await bot.send_rich_message(
            chat_id=chat_id, rich_message=_nitro_rich_message(simulation, players),
        )
    except TelegramAPIError:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text="⚡ Нитро перед стартом:\n" + "\n".join(
                    f"{player.title}: {simulation.nitro[index]}"
                    for index, player in enumerate(players)
                ),
            )
        except TelegramAPIError:
            logger.exception("Не удалось опубликовать запас нитро в чате %s", chat_id)
    create_race_gif(
        game_state, players, chat_id=chat_id,
        output_path=f"race_{chat_id}.gif", frame_count=400, duration=2,
        simulation_result=simulation,
    )

    medals = {
        1: "🥇", 2: "🥈", 3: "🥉", 4: "4️⃣", 5: "5️⃣",
        6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣", 10: "🔟",
    }
    current_day = current_day or datetime.now().date()
    result_text = Text("🏁 Результаты «Гонки: нитро и интриги»\n\n")
    if timed_out:
        result_text += "⏱ Время вышло: незавершённые решения заменены безопасными.\n\n"
    for place, player_idx in enumerate(simulation.winners, start=1):
        player = players[player_idx]
        prize = simulation.prizes.get(place, 0)
        result_text += f"{medals.get(place, place)} .. "
        result_text += Spoiler(f"{player.title:…<20}")
        result_text += f"  ⚡{simulation.nitro[player_idx]} +{prize} 💟\n"
        if prize:
            player.attributes["karma"] = player.get_karma() + prize
            await AuditService(session).log_action(
                player.id, UserActionType.GAME_KARMA, current_day, prize,
                f"{player.title} За {place} место в заезде получил {prize:+d} кармы",
            )
    result_text += "\n#гонки"
    await remove_state(chat_id, session)
    await session.commit()
    _unschedule_deadline(chat_id)
    await bot.send_animation(
        chat_id=chat_id, animation=FSInputFile(f"race_{chat_id}.mp4"),
    )
    try:
        await bot.send_rich_message(
            chat_id=chat_id,
            rich_message=_result_rich_message(simulation, players, game_state),
        )
    except TelegramBadRequest:
        await bot.send_message(chat_id=chat_id, **result_text.as_kwargs())
    return True


async def process_race_deadline(bot, chat_id: int):
    """Автоматически начать заезд по дедлайну под общей блокировкой."""
    from config.database import db_pool
    from middlewares.lock_operation import shared_locks
    import asyncio

    lock = shared_locks.setdefault("race", asyncio.Lock())
    async with lock:
        async with db_pool() as session:
            game_state = await get_state(chat_id, session)
            if game_state is None or not game_state.deadline_reached(datetime.now()):
                return
            await execute_race(bot, chat_id, session)


@router.callback_query(MyCallback.filter(F.action == "race_start_now"),
                       flags={"check_admin": True, "lock_operation": "race",
                              "long_operation": "upload_video"})
async def race_start_now_callback(callback: CallbackQuery, session, current_day):
    """Разрешить администратору стартовать раньше после всех подтверждений."""
    game_state = await get_state(callback.message.chat.id, session)
    if game_state is None or game_state.phase != "selection":
        await send_alarm(callback, "⚠️ Окно выбора уже закрыто.")
        return
    if not game_state.all_ready():
        await send_alarm(callback, "⚠️ Не все участники подтвердили выбор.")
        return
    await callback.answer("Заезд начинается")
    await execute_race(
        callback.message.bot, callback.message.chat.id, session, current_day,
    )


async def get_media(players):
    """Подготовить изображение лобби или стартовую сетку участников."""
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
    """Собрать правила, прогноз, призы и список участников для лобби."""
    content = Bold(f"🏁 Игра «Гонки» 🏎️🚙🚗🚌🛻🚜\n\n")
    content += "После закрытия набора участники тайно выбирают шины, перевозки нитро, защиту и план гонки.\n\n"
    content += (
        "Каждая перевозка: попытайтесь забрать 1 нитро у одного соперника и передать другому. "
        "Если кража заблокирована, платите своим нитро; если подарок заблокирован, "
        "нитро остаётся вам. Защищайтесь от конкретных игроков. "
        "Нитро сильнее на солнечной трассе и слабее в дождь: выбирайте "
        "ранний рывок, ровный темп или финиш с учётом прогноза. "
        "После выбора виден только итоговый запас нитро каждого, но не маршруты и планы гонки.\n\n"
    )
    content += (
        f"На выбор даётся 1 час. Когда все подтвердят выбор, "
        f"администратор сможет запустить заезд раньше.\n"
        f"Вступительный взнос - {FEE} 💟.\n\n"
    )
    count = len(game_state.player_ids)
    content += as_key_value("Количество участников", count)
    content += '\n'
    if count >= MIN_PLAYERS:
        prizes = allocate_prizes(count, FEE)
        content += Text("\nЗа 🥇 место выигрыш: ") + Code(f"{prizes[1]:+4d} 💟")
        content += Text("\nЗа 🥈 место выигрыш: ") + Code(f"{prizes[2]:+4d} 💟")
        content += Text("\nЗа 🥉 место выигрыш: ") + Code(f"{prizes[3]:+4d} 💟")
        content += Text("\nЗа 4️⃣ место выигрыш: ") + Code(f"{prizes[4]:+4d} 💟")
        content += Text("\nЗа 5️⃣ место выигрыш: ") + Code(f"{prizes[5]:+4d} 💟")
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
    """Показать доступные кнопки набора и открытия окна выбора."""
    builder = InlineKeyboardBuilder()
    keyboard_sizes = []
    players_count = len(game_state.player_ids)
    if game_state.phase == "lobby" and players_count < MAX_PLAYERS:
        add_button(f"Участвовать (плата 💟 {FEE} кармы)", "join_race", 0, builder, style='primary')
        keyboard_sizes.append(1)

    if game_state.phase == "lobby" and players_count >= MIN_PLAYERS:
        add_button("🏁 Начать гонку!", "start_race", 0, builder, style='danger')
        keyboard_sizes.append(1)
    builder.adjust(*keyboard_sizes)
    return builder
