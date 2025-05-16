import logging
import re
from datetime import datetime
from typing import Optional, List, Tuple, Dict

from aiogram import Router, F
from aiogram.types import Message
from aiogram.utils.formatting import Text, Bold, Code, HashTag, Italic, TextLink
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from handlers.driver_callback import add_button, MyCallback
from models.driver import Driver
from models.user_audit import UserActionType
from services.audit_service import AuditService
from services.driver_service import DriverService
from services.notification_sender import send_reply, send_alarm

router = Router()
logger = logging.getLogger(__name__)

def get_cost(price):
    vat = max(1, round(price * 0.1))
    return price + vat


@router.message(
    F.text.regexp(r"(?i).*новый магазин добрых дел.*"),
    flags={"lock_operation": "shop", "check_driver": True})
async def new_shop(message: Message, session: AsyncSession, driver: Driver, current_day, is_private):
    if not is_private:
        await message.answer("Команда недоступна в общих чатах.")
        return

    items = parse_items(message.text)
    driver.attributes["shop_id"] = 1 + driver.attributes.get("shop_id", 0)
    driver.attributes["shop_items"] = items

    await AuditService(session).log_action(driver.id, UserActionType.SHOP, current_day, len(items),
                                           f'{driver.title} создает магазин добрых дел с {len(items)} предметами')

    builder = await get_shop_keyboard(driver, items)
    content = Bold("Магазин добрых дел создан!")
    content += '\n\n'
    content += Text("Чтобы отобразить его в чате - напишите следующую команду: ")
    content += Code("Открыть магазин")
    content += '\n\n'
    content += Text("Чтобы закрыть его - напишите следующую команду (можно и в ЛС): ")
    content += Code("Закрыть магазин")
    content += Text("\nИли ") + Code("Новый магазин добрых дел") + Text(" в ЛС без указания товаров.")
    content += '\n\n'
    content += Text("Кнопка ") + Bold("'❎ Свернуть лавочку'") + Text(" скрывает магазин в чате.\n")
    content += Text("Заново отобразить его можно командой ") + Code("Открыть магазин") + Text(".")
    content += '\n\n'
    content += Text("Приятных добрых дел!")
    content += '\n\n'
    content += Italic("В стоимость включен НДС 10% (минимум 1 💟).")
    content += '\n\n'
    content += HashTag("#магазин")
    await send_reply(message, content, builder)


@router.message(
    F.text.regexp(r"(?i).*открыть магазин"),
    flags={"lock_operation": "shop", "check_driver": True})
async def show_shop(message: Message, session: AsyncSession, driver: Driver, current_day, is_private):
    items = driver.attributes.get("shop_items", [])
    if not items:
        await send_alarm(message, "⚠️ Магазин не создан")
        return
    content, builder = await get_shop_content_and_keyboard(driver, is_private)
    await send_reply(message, content, builder)
    if not is_private:
        await AuditService(session).log_action(driver.id, UserActionType.SHOP, current_day, 0,
                                               f'{driver.title} показывает магазин добрых дел')


@router.message(
    F.text.regexp(r"(?i).*закрыть магазин"),
    flags={"lock_operation": "shop", "check_driver": True})
async def close_shop(message: Message, session: AsyncSession, driver: Driver, current_day, is_private):
    items = []
    driver.attributes["shop_id"] = 1 + driver.attributes.get("shop_id", 0)
    driver.attributes["shop_items"] = items

    await AuditService(session).log_action(driver.id, UserActionType.SHOP, current_day, len(items),
                                           f'{driver.title} закрывает магазин добрых дел')
    builder = InlineKeyboardBuilder()
    await send_reply(message, Bold("✖️ Магазин закрыт!"), builder)


@router.callback_query(MyCallback.filter(F.action == "hide-shop"),
                       flags={"lock_operation": "shop", "check_driver": True, "check_callback": True})
async def hide_shop(callback, session, driver, current_day, is_private):
    try:
        await send_alarm(callback, "❎ Магазин скрыт!\n\nПокажите его снова с помощью команды 'Открыть магазин'")
        await callback.message.delete()

        if not is_private:
            await AuditService(session).log_action(driver.id, UserActionType.SHOP, current_day, 0,
                                                   f'{driver.title} скрывает магазин добрых дел')

    except:
        pass


@router.callback_query(MyCallback.filter(F.action == "buy-item"),
                       flags={"lock_operation": "shop", "check_driver": True})
async def buy_item(callback, callback_data: MyCallback, session, driver, current_day, is_private):
    seller = await DriverService(session).get_by_chat_id(callback_data.user_id)
    if not seller:
        await send_alarm(callback, "⚠️ Продавец не найден")
        await callback.message.delete()
        return
    if callback_data.spot_id != seller.attributes.get("shop_id", 0):
        await send_alarm(callback, "⚠️ Продавец прикрыл лавочку")
        await callback.message.delete()
        return
    items = seller.attributes["shop_items"]
    if items is None or callback_data.day_num >= len(items):
        await send_alarm(callback, "⚠️ Товар не найден")
        await callback.message.delete()
        return

    item = items[callback_data.day_num]
    if item["count"] is not None and item["count"] <= item.get("sold", 0):
        await send_alarm(callback, "⚠️ Товар закончился")
        content, builder = await get_shop_content_and_keyboard(seller, is_private)
        await send_reply(callback, content, builder)
        return

    if seller.id == driver.id:
        await send_alarm(callback, "⚠️ Нельзя купить у себя")
        return

    if get_cost(item["price"]) > driver.get_karma():
        await send_alarm(callback, "⚠️ У вас недостаточно кармы")
        return

    driver.attributes["karma"] = driver.get_karma() - get_cost(item["price"])
    seller.attributes["karma"] = seller.get_karma() + item["price"]
    await AuditService(session).log_action(driver.id, UserActionType.SHOP_KARMA, current_day, -get_cost(item["price"]),
                                           f'{driver.title} купил товар "{item["description"]}" у {seller.title}')
    await AuditService(session).log_action(seller.id, UserActionType.SHOP_KARMA, current_day, item["price"],
                                           f'{seller.title} продал товар "{item["description"]}" {driver.title}')
    item["sold"] = item.get("sold", 0) + 1
    seller.attributes["shop_items"] = items
    await AuditService(session).log_action(driver.id, UserActionType.SHOP, current_day, 1,
                                           f'{driver.title} купил товар "{item["description"]}" у {seller.title}')
    await AuditService(session).log_action(seller.id, UserActionType.SHOP, current_day, -1,
                                           f'{seller.title} продал товар "{item["description"]}" {driver.title}')
    await send_alarm(callback,
                     f"✅ '{item['description']}' куплен!\n\nПродавец: {seller.title}\n\nВаш баланс: {driver.get_karma()} 💟")
    content, builder = await get_shop_content_and_keyboard(seller, is_private)
    await send_reply(callback, content, builder)
    try:
        await callback.bot.send_message(chat_id=driver.chat_id,
                                        text=f"✅ '{item['description']}' куплен за {get_cost(item['price'])} 💟\n\nПродавец: {seller.title}\n\nВаш баланс: {driver.get_karma()} 💟")
    except Exception as e:
        logging.error(f"Error in send message: {e}")
    try:
        await callback.bot.send_message(chat_id=seller.chat_id,
                                        text=f"✅ '{item['description']}' продан за {item['price']} 💟\n\nПокупатель: {driver.title}\n\nВаш баланс: {seller.get_karma()} 💟")
    except Exception as e:
        logging.error(f"Error in send message: {e}")


async def get_shop_content_and_keyboard(driver, is_private):
    content = Text("")
    if is_private:
        content += Italic("‼️Напишите команду в общем чате!")
        content += '\n\n\n'
    is_woman = driver.attributes.get("gender", "M") == "F"
    content += TextLink(driver.description, url=f"tg://user?id={driver.chat_id}")
    content += Text(f" открыл{'а' if is_woman else ''} ")
    content += Bold(f"Магазин добрых дел 🫶")
    content += '\n\n'
    content += Text("Приятных добрых дел!")
    content += '\n\n'
    content += Italic("В стоимость включен НДС 10% (минимум 1 💟).")
    content += '\n\n'
    content += HashTag("#магазин")
    content += '\n\n'
    content += Italic(f"Обновлено {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    builder = await get_shop_keyboard(driver, driver.attributes.get("shop_items", []))
    return content, builder


async def get_shop_keyboard(driver, items):
    builder = InlineKeyboardBuilder()
    for idx, item in enumerate(items):
        is_sold_out = item["count"] is not None and item["count"] <= item.get("sold", 0)
        if is_sold_out:
            add_button(f"❎ → {item['description']} "
                       f"[{(str(item['count'] - item.get("sold", 0)) + " / " + str(item['count']))}]",
                       "pass", driver.chat_id, builder,
                       spot_id=driver.attributes.get("shop_id", 0),
                       day_num=idx)
            continue
        add_button(f"{get_cost(item['price'])} 💟 → {item['description']} "
                   f"[{"∞" if item['count'] is None else (str(item['count'] - item.get("sold", 0)) + " / " + str(item['count']))}]",
                   "buy-item", driver.chat_id, builder,
                   spot_id=driver.attributes.get("shop_id", 0),
                   day_num=idx)
    add_button("❎ Свернуть лавочку", "hide-shop", driver.chat_id, builder)
    builder.adjust(1)
    return builder


def parse_line(line: str) -> Tuple[int, str, Optional[int]]:
    """
    Разбирает строку формата:
        <цена> - <описание> (<количество>)
    или без количества:
        <цена> - <описание>

    Возвращает
        price: int
        description: str
        count: Optional[int]

    Примеры:
        parse_line("1 - поделюсь конфеткой (5)")  # (1, "поделюсь конфеткой", 5)
        parse_line("2 - обнимашки")               # (2, "обнимашки", None)
    """
    # Регулярное выражение: группа 1 — цена, группа 2 — описание, группа 3 — количество (опционально)
    pattern = r"^\s*(\d+)\s*-\s*(.+?)(?:\s*\((\d+)\))?\s*$"
    match = re.match(pattern, line)
    if not match:
        return 0, "Строка не соответствует формату", None

    price = int(match.group(1))
    description = match.group(2).strip()
    count = int(match.group(3)) if match.group(3) is not None else None
    return price, description, count


def parse_items(text: str) -> List[Dict[str, Optional[int]]]:
    """
    Разбирает несколько строк текста, возвращает список словарей с ключами:
        - price: int
        - description: str
        - count: Optional[int]

    Игнорирует пустые строки.
    """
    result = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        price, desc, count = parse_line(line)
        if price > 0:
            result.append({"price": price, "description": desc, "count": count, })
    return result
