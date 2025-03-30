import re
from datetime import datetime, timedelta
from io import BytesIO

from aiogram import Router, F
from aiogram.filters import Command, or_f
from aiogram.types import Message, BufferedInputFile, CallbackQuery
from aiogram.utils.formatting import Text, Bold
from aiogram.utils.keyboard import InlineKeyboardBuilder

from models.driver import Driver
from services.parking_service import ParkingService
from utils.map_generator import generate_parking_map

router = Router()


@router.message(F.text.regexp(r"^(\d+)$").as_("digits"), flags={"check_driver": True})
async def any_digits_handler(message: Message, digits: re.Match[str]):
    await message.answer(str(digits))


@router.message(F.text.regexp(r"(?i)(.*пока.* карт(а|у) на завтра)|(.*карт(а|у) парковки на завтра)"),
                flags={"long_operation": "upload_photo", "check_driver": True})
async def map_tomorrow_command(message: Message, session, driver, current_day, is_private):
    day = current_day + timedelta(days=1)

    # Получаем данные для карты
    parking_service = ParkingService(session)
    spots, reservations = await parking_service.get_spots_with_reservations(day)

    # Генерируем карту
    img = generate_parking_map(
        parking_spots=spots,
        reservations_data=reservations,
        driver=driver if is_private else None,
        use_spot_status=False
    )

    img_buffer = BytesIO()
    img.save(img_buffer, format="PNG")
    img_buffer.seek(0)

    # Отправка изображения
    await message.answer_photo(
        BufferedInputFile(img_buffer.getvalue(), filename="map.png"),
        caption=f"Карта парковки на завтра {day.strftime('%d.%m.%Y')}\n\n"
                f"🔴 - зарезервировано\n"
                f"{'🟡 - зарезервировано Вами\n' if is_private else ''}"
                f"🟢 - свободно"
    )
    if is_private:
        await spot_selection(message, session, driver, True)

@router.message(or_f(Command("map"), F.text.regexp(r"(?i)(.*пока.* карт(а|у))|(.*карт(а|у) парковки)")),
                flags={"long_operation": "upload_photo", "check_driver": True})
async def map_command(message: Message, session, driver, current_day, is_private):
    # Получаем данные для карты
    parking_service = ParkingService(session)
    spots, reservations = await parking_service.get_spots_with_reservations(current_day)

    # Генерируем карту
    img = generate_parking_map(
        parking_spots=spots,
        reservations_data=reservations,
        driver=driver if is_private else None
    )

    img_buffer = BytesIO()
    img.save(img_buffer, format="PNG")
    img_buffer.seek(0)

    # Отправка изображения
    await message.answer_photo(
        BufferedInputFile(img_buffer.getvalue(), filename="map.png"),
        caption=f"Карта парковки на {current_day.strftime('%d.%m.%Y')}.\n"
                f"(Обновлено {datetime.now().strftime('%d.%m.%Y %H:%M')})\n\n"
                f"🔴 - зарезервировано\n"
                f"{'🟡 - зарезервировано Вами\n' if is_private else ''}"
                f"🟢 - свободно"
    )
    if is_private:
        await spot_selection(message, session, driver, True)


@router.callback_query(F.data.startswith("edit-schedule"), flags={"check_driver": True})
async def handle_spot_selection(callback: CallbackQuery, session, driver):
    await spot_selection(callback.message, session, driver, True)
    await callback.answer()


@router.callback_query(F.data.startswith("choose-spots"), flags={"check_driver": True})
async def handle_spot_selection(callback: CallbackQuery, session, driver):
    await spot_selection(callback.message, session, driver, False)


async def spot_selection(message: Message, session, driver: Driver, is_new: bool):
    # Добавляем кнопки выбора мест
    builder = InlineKeyboardBuilder()
    # Получаем данные для карты
    spots = driver.my_spots()

    if not spots:
        builder.button(
            text=f"Показать очередь",
            switch_inline_query_current_chat=f"Показать очередь"
        )
        await message.answer(
            f"У вас нет доступных мест для бронирования.\n\n"
            f"Обратитесь к администратору или используйте команды работы с очередью.",
            reply_markup=builder.as_markup()
        )
        return

    for spot in spots:
        builder.button(
            text=f"{spot.id}",
            callback_data=f"select-spot_{spot.id}"
        )
    builder.adjust(3)

    content = Text(
        "📅 Тут вы можете забронировать парковку по дням недели.\n",
        "Укажите, по каким дням недели вы приезжаете.",
        Bold("\n\nВыберите место для бронирования:"))

    if is_new:
        await message.answer(
            **content.as_kwargs(),
            reply_markup=builder.as_markup()
        )
    else:
        await message.edit_text(
            **content.as_kwargs(),
            reply_markup=builder.as_markup()
        )
