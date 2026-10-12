import re

from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InputRichBlockSectionHeading,
    InputRichBlockTable,
    InputRichMessage,
    RichBlockTableCell,
)
from aiogram.utils.formatting import Text, Bold, as_key_value, as_list, TextLink, as_marked_section
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from config import constants
from handlers.driver_callback import add_button, MyCallback
from models.driver import Driver
from models.user_audit import UserActionType
from services.audit_service import AuditService
from services.driver_service import DriverService
from services.notification_sender import send_reply, send_rich_reply
from services.telegram_ui import answer_rich

PERIOD_IN_DAYS = 30

router = Router()


@router.callback_query(MyCallback.filter(F.action == "achievements"),
                       flags={"check_driver": True, "check_callback": True})
async def show_achievements(event, session, driver: Driver, current_day):
    content = Text('🪪 ', TextLink(driver.title, url=f"tg://user?id={driver.chat_id}"), "\n",
                   f"{driver.description}", '\n\n')
    content += Bold("🏆 Мои достижения:")
    content += '\n\n'
    content += get_achievement_row("Магнат 💟", driver.get_karma(), 100, 500, 5000)
    content += '\n'

    actions = await AuditService(session).get_actions_by_period(driver.id, PERIOD_IN_DAYS, current_day)
    last_actions = dict()
    # список последних действий в каждом дне, если входит в список TAKE_SPOT, RELEASE_SPOT, JOIN_QUEUE, LEAVE_QUEUE
    for a in actions:
        if (a.action in [UserActionType.TAKE_SPOT, UserActionType.RELEASE_SPOT, UserActionType.JOIN_QUEUE,
                         UserActionType.LEAVE_QUEUE]
                and (a.action_time.hour >= constants.new_day_begin_hour or a.action_time.hour < 14)):
            last_actions[a.current_day] = a

    regular = len(set(a.current_day for a in last_actions.values() if a.action == UserActionType.TAKE_SPOT))
    content += get_achievement_row("Завсегдатай 🍸", regular, 5, 10, 20)

    generous_soul = len(set(a.current_day for a in last_actions.values() if a.action == UserActionType.RELEASE_SPOT))
    content += get_achievement_row("Щедрая душа 💛", generous_soul, 2, 3, 5)

    stoic = len(set(a.current_day for a in last_actions.values() if
                    a.action in [UserActionType.JOIN_QUEUE, UserActionType.LEAVE_QUEUE]))
    content += get_achievement_row("Стоик 🪨", stoic, 2, 3, 5)

    racer = sum(1 for a in actions if a.action == UserActionType.GAME_KARMA and a.num == -5)
    content += get_achievement_row("Гонщик 🏎️", racer, 3, 7, 15)

    traveler = len(set(a.num for a in actions if a.action == UserActionType.TAKE_SPOT))
    content += get_achievement_row("Путешественник 🌏", traveler, 2, 3, 5, 2)

    rainbow_fortune = max_unique_length([a.num for a in actions if a.action == UserActionType.DRAW_KARMA])
    content += get_achievement_row("Радуга фортуны 🌈", rainbow_fortune, 4, 5, 6, 3)

    repeat_karma = max_consecutive_length([a.num for a in actions if a.action == UserActionType.DRAW_KARMA])
    content += get_achievement_row("По колее 🚗", repeat_karma, 3, 4, 5, 2)

    queue_expert = len(set(a.current_day for a in actions if a.action == UserActionType.LEAVE_QUEUE))
    content += get_achievement_row("Очередной эксперт 🏃", queue_expert, 2, 5, 10)

    expensive = sum(-a.num for a in actions if a.action == UserActionType.SHOP_KARMA and a.num < 0)
    content += get_achievement_row("Дорогой клиент 🤑", expensive, 5, 20, 50)

    shopaholic = sum(1 for a in actions if a.action == UserActionType.SHOP_KARMA and a.num < 0)
    content += get_achievement_row("Шопоголик 🏷️", shopaholic, 2, 5, 10)

    # TODO: add achievements

    builder = InlineKeyboardBuilder()
    add_button("ℹ️ Описание ачивок...", "achievements-info", driver.chat_id, builder)
    add_button("⬅️ Назад", "show-status", driver.chat_id, builder)
    builder.adjust(1)
    await send_reply(event, content, builder)


def get_achievement_row(title: str, current_value: int, bronze: int, silver: int, gold: int, threshold: int = 1):
    if current_value >= gold:
        return Bold(f"🥇 {title}") + f" [{current_value}/{gold}]\n"
    elif current_value >= silver:
        return Bold(f"🥈 {title}") + f" [{current_value}/{gold}]\n"
    elif current_value >= bronze:
        return Bold(f"🥉 {title}") + f" [{current_value}/{silver}]\n"
    elif current_value >= threshold:
        return Bold(f"👍 {title}") + f" [{current_value}/{bronze}]\n"
    else:
        return ''


@router.callback_query(MyCallback.filter(F.action == "achievements-info"),
                       flags={"check_driver": True, "check_callback": True})
async def show_achievements_info(event, session, driver: Driver):
    content = as_list(
        Bold(f"🏆 Описание достижений"),
        as_marked_section(
            Bold("Общие ачивки:"),
            as_key_value("💟 Магнат", "Ачивка за текущий баланс кармы"),
            marker="    ",
        ),
        as_marked_section(
            Bold(f"Ачивки за последние {PERIOD_IN_DAYS} дней:"),
            as_key_value("🍸 Завсегдатай", "Насколько часто занимаете парковку"),
            as_key_value("💛 Щедрая душа", f"Освободил парковку после {constants.new_day_begin_hour}:00, но до 10:00"),
            # и не занял после
            as_key_value("🌈 Радуга фортуны", "Разное количество кармы несколько дней подряд"),
            as_key_value("🚗 По колее", "Одно и то же количество кармы несколько дней подряд"),
            as_key_value("🏎️ Гонщик", "Участие в игре «Гонки»"),
            as_key_value("🤑 Дорогой клиент", "Сумма покупок в магазине"),
            as_key_value("🏷️ Шопоголик", "Количество покупок в магазине"),
            marker="    ",
        ),
        as_marked_section(
            Bold("Редкие ачивки:"),
            Bold("🪨 Стоик"),  # Вышел из очереди в течение рабочего дня и не приехал на парковку
            Bold("🌏 Путешественник"),  # Занимаете разные парковочные места
            Bold("🏃 Очередной эксперт"),  # Вышел из очереди в течение рабочего дня
            marker="    ",
        ),
        sep="\n\n",
    )
    builder = InlineKeyboardBuilder()
    add_button("⬅️ Назад", "achievements", driver.chat_id, builder)
    builder.adjust(1)
    await send_reply(event, content, builder)


@router.message(F.text.regexp(r"(?i).*топ (\d+)?.*карм.* нед").as_("match"), flags={"check_driver": True})
async def top_karma_week(message: Message, session: AsyncSession, match: re.Match):
    limit = int(match.group(1) if match.group(1) is not None else 10)
    await show_karma_week(message, session, limit, 0, '')


@router.callback_query(MyCallback.filter(F.action == "karma-week"), flags={"check_driver": True})
async def top_karma_week_callback(callback: CallbackQuery, callback_data: MyCallback, session: AsyncSession):
    limit = callback_data.spot_id
    act = callback_data.event_type
    sign = callback_data.day_num
    await show_karma_week(callback, session, limit, sign, act)


@router.message(F.text.regexp(r"(?i).*топ (\d+)?.*карм").as_("match"), flags={"check_driver": True})
async def top_karma(message: Message, session: AsyncSession, match: re.Match):
    limit = int(match.group(1) if match.group(1) is not None else 10)
    drivers = await DriverService(session).get_top_karma_drivers(limit)
    rows = [[
        _cell("Место", header=True),
        _cell("Водитель", header=True),
        _cell("Карма", header=True),
    ]]
    fallback = [f"🏆 Топ {len(drivers)} кармы водителей:"]
    for index, top_driver in enumerate(drivers, start=1):
        rows.append([
            _cell(str(index), align="center"),
            _cell(top_driver.title),
            _cell(str(top_driver.get_karma()), align="center"),
        ])
        fallback.append(f"{index}. {top_driver.get_karma()} — {top_driver.title}")
    await answer_rich(
        message,
        InputRichMessage(
            blocks=[
                InputRichBlockSectionHeading(
                    text=f"🏆 Топ {len(drivers)} кармы водителей", size=1
                ),
                InputRichBlockTable(
                    cells=rows,
                    is_bordered=True,
                    is_striped=True,
                    is_compact=True,
                ),
            ]
        ),
        fallback_text="\n".join(fallback),
    )


def _cell(text, *, header: bool = False, align: str = "left"):
    return RichBlockTableCell(
        text=text,
        align="center" if header else align,
        valign="middle",
        is_header=True if header else None,
    )


async def show_karma_week(event, session, limit, sign, act):
    result = await AuditService(session).get_weekly_karma(limit, sign, act)
    rows = [[
        _cell("Место", header=True),
        _cell("Водитель", header=True),
        _cell("Карма за неделю", header=True),
    ]]
    fallback = [f"🏆 Топ {len(result)} кармы водителей за неделю:"]
    for index, (total, description) in enumerate(result, start=1):
        rows.append([
            _cell(str(index), align="center"),
            _cell(description),
            _cell(str(total), align="center"),
        ])
        fallback.append(f"{index}. {total} — {description}")
    builder = InlineKeyboardBuilder()
    add_karma_button(builder, '', 0, limit, "💟", sign, act)
    add_karma_button(builder, '', 1, limit, "∑+", sign, act)
    add_karma_button(builder, '', -1, limit, "∑-", sign, act)
    add_karma_button(builder, UserActionType.DRAW_KARMA.name, 0, limit, "🎲", sign, act)
    add_karma_button(builder, UserActionType.GET_ADMIN_KARMA.name, 0, limit, "🫶", sign, act)
    add_karma_button(builder, UserActionType.GAME_KARMA.name, +1, limit, "🕹+", sign, act)
    add_karma_button(builder, UserActionType.GAME_KARMA.name, -1, limit, "🕹-", sign, act)
    add_karma_button(builder, UserActionType.SHOP_KARMA.name, +1, limit, "🏪+", sign, act)
    add_karma_button(builder, UserActionType.SHOP_KARMA.name, -1, limit, "🏪-", sign, act)
    builder.adjust(1, 2, 1, 1, 2, 2)
    await send_rich_reply(
        event,
        InputRichMessage(
            blocks=[
                InputRichBlockSectionHeading(
                    text=f"🏆 Топ {len(result)} кармы водителей за неделю",
                    size=1,
                ),
                InputRichBlockTable(
                    cells=rows,
                    is_bordered=True,
                    is_striped=True,
                    is_compact=True,
                ),
            ]
        ),
        builder,
        fallback_text="\n".join(fallback),
    )


def add_karma_button(builder, button_act, button_sign, limit, text, sign, act):
    if button_sign == sign and (button_act == act or (not button_act and not act)):
        add_button("✔️ " + text, "pass", 0, builder)
    else:
        add_button(text, "karma-week", 0, builder, spot_id=limit, day_num=button_sign, event_type=button_act)


def max_unique_length(nums):
    max_len = 0
    current_set = set()
    left = 0
    right = 0
    n = len(nums)
    while right < n:
        if nums[right] not in current_set:
            current_set.add(nums[right])
            right += 1
            max_len = max(max_len, right - left)
        else:
            current_set.remove(nums[left])
            left += 1
    return max_len


def max_consecutive_length(nums):
    if not nums:
        return 0

    max_length = 1
    current_length = 1

    for i in range(1, len(nums)):
        if nums[i] == nums[i - 1]:
            current_length += 1
            if current_length > max_length:
                max_length = current_length
        else:
            current_length = 1

    return max_length
