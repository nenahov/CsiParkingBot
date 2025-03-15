from datetime import datetime
from io import BytesIO

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.parking_service import ParkingService
from utils.map_generator import generate_parking_map

router = Router()


@router.message(Command("map"), flags={"long_operation": "upload_photo", "check_driver": True})
async def map_command(message: Message, session, driver):
    # Получаем текущий день недели (0 - понедельник, 6 - воскресенье)
    current_day = datetime.today().weekday()

    # # Получаем данные пользователя
    # driver_service = DriverService(session)
    # driver = await driver_service.get_by_chat_id(message.from_user.id)

    if not driver or not driver.enabled:
        await message.answer("Сначала зарегистрируйтесь!")
        return

    # Получаем данные для карты
    parking_service = ParkingService(session)
    spots, reservations = await parking_service.get_spots_with_reservations(current_day)

    # Генерируем карту
    img = generate_parking_map(
        parking_spots=spots,
        reservations_data=reservations,
        current_user_id=driver.chat_id
    )

    img_buffer = BytesIO()
    img.save(img_buffer, format="PNG")
    img_buffer.seek(0)

    # Отправка изображения
    await message.answer_photo(
        BufferedInputFile(img_buffer.getvalue(), filename="map.png"),
        caption=f"Карта парковки на {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    if message.chat.type == 'private':
        await spot_selection(message, session, True)


@router.callback_query(F.data.startswith("choose-spots"))
async def handle_spot_selection(callback: CallbackQuery, session):
    await spot_selection(callback.message, session, False)


async def spot_selection(message: Message, session, is_new: bool):
    # Добавляем кнопки выбора мест
    builder = InlineKeyboardBuilder()
    # Получаем данные для карты
    parking_service = ParkingService(session)
    spots = await parking_service.get_all_spots()

    for spot in spots:
        builder.button(
            text=f"{spot.id}",
            callback_data=f"select-spot_{spot.id}"
        )
    builder.adjust(3)

    if is_new:
        await message.answer(
            "Выберите место для бронирования:",
            reply_markup=builder.as_markup()
        )
    else:
        await message.edit_text(
            "Выберите место для бронирования:",
            reply_markup=builder.as_markup()
        )
