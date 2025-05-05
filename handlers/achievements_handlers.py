from aiogram import Router, F
from aiogram.utils.formatting import Text, Bold, as_key_value, as_list, TextLink, as_marked_section
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.driver_callback import add_button, MyCallback
from models.driver import Driver
from models.user_audit import UserActionType
from services.audit_service import AuditService
from services.notification_sender import send_reply

router = Router()


@router.callback_query(MyCallback.filter(F.action == "achievements"),
                       flags={"check_driver": True, "check_callback": True})
async def show_achievements(event, session, driver: Driver, current_day):
    content = Text('🪪 ', TextLink(driver.title, url=f"tg://user?id={driver.chat_id}"), "\n",
                   f"{driver.description}", '\n\n')
    content += Bold("🏆 Мои достижения:")
    content += '\n\n'
    content += get_achievement_row("Магнат 💟", driver.get_karma(), 50, 100, 200)
    content += '\n'

    actions = await AuditService(session).get_actions_by_period(driver.id, 30, current_day)
    last_actions = dict()
    # список последних действий в каждом дне, если входит в список TAKE_SPOT, RELEASE_SPOT, JOIN_QUEUE, LEAVE_QUEUE
    for a in actions:
        if (a.action in [UserActionType.TAKE_SPOT, UserActionType.RELEASE_SPOT, UserActionType.JOIN_QUEUE,
                         UserActionType.LEAVE_QUEUE]
                and (a.action_time.hour >= 19 or a.action_time.hour < 14)):
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

    omnivorous = len(set(a.num for a in actions if a.action == UserActionType.TAKE_SPOT))
    content += get_achievement_row("Всеядный 🍽️", omnivorous, 2, 3, 5, 2)

    queue_expert = len(set(a.current_day for a in actions if a.action == UserActionType.LEAVE_QUEUE))
    content += get_achievement_row("Очередной эксперт 🏃", queue_expert, 2, 5, 10)

    # TODO: add achievements

    builder = InlineKeyboardBuilder()
    add_button("ℹ️ Описание ачивок...", "achievements-info", driver.chat_id, builder)
    add_button("⬅️ Назад", "show-status", driver.chat_id, builder)
    builder.adjust(1)
    await send_reply(event, content, builder)


def get_achievement_row(title: str, current_value: int, bronze: int, silver: int, gold: int, threshold: int = 1) -> str:
    if current_value >= gold:
        return f"🥇 {title}\n"
    elif current_value >= silver:
        return f"🥈 {title} [{current_value}/{gold}]\n"
    elif current_value >= bronze:
        return f"🥉 {title} [{current_value}/{silver}]\n"
    elif current_value >= threshold:
        return f"👍 {title} [{current_value}/{bronze}]\n"
    else:
        return ''


@router.callback_query(MyCallback.filter(F.action == "achievements-info"),
                       flags={"check_driver": True, "check_callback": True})
async def show_achievements_info(event, session, driver: Driver):
    # TODO: add achievements

    content = as_list(
        Bold(f"🏆 Описание достижений"),
        as_marked_section(
            Bold("Общие ачивки:"),
            as_key_value("💟 Магнат", "Ачивка за текущий баланс кармы"),
            marker="    ",
        ),
        as_marked_section(
            Bold(f"Ачивки за последние 30 дней:"),
            as_key_value("🍸 Завсегдатай", "Насколько часто занимаете парковку"),
            as_key_value("💛 Щедрая душа", "Освободил парковку после 19:00, но до 10:00"),  # и не занял после
            as_key_value("🏎️ Гонщик", "За количество участий в игре «Гонки»"),
            marker="    ",
        ),
        as_marked_section(
            Bold("Редкие ачивки:"),
            "🍽️ Всеядный",  # Занимаете разные парковочные места
            "🏃 Очередной эксперт",  # Вышел из очереди в течение рабочего дня
            "🪨 Стоик",  # Вышел из очереди в течение рабочего дня и не приехал на парковку
            marker="    ",
        ),
        sep="\n\n",
    )
    builder = InlineKeyboardBuilder()
    add_button("⬅️ Назад", "achievements", driver.chat_id, builder)
    builder.adjust(1)
    await send_reply(event, content, builder)
