from datetime import datetime
from io import BytesIO

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.database import async_session_maker
from services.driver_service import DriverService
from services.parking_service import ParkingService
from utils.map_generator import generate_parking_map

router = Router()


@router.message(Command("map"))
async def map_command(message: Message):
    async with async_session_maker() as session:
        # Получаем текущий день недели (0 - понедельник, 6 - воскресенье)
        current_day = datetime.today().weekday()

        # Получаем данные пользователя
        driver_service = DriverService(session)
        driver = await driver_service.get_by_chat_id(message.from_user.id)

        if not driver:
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
            caption="Карта парковки"
        )
        await spot_selection(message, True)


@router.callback_query(F.data.startswith("choose-spots"))
async def handle_spot_selection(callback: CallbackQuery):
    await spot_selection(callback.message, False)


async def spot_selection(message: Message, is_new: bool):
    async with async_session_maker() as session:
        # Добавляем кнопки выбора мест
        builder = InlineKeyboardBuilder()
        # Получаем данные для карты
        parking_service = ParkingService(session)
        spots = await parking_service.get_all_spots()

        for spot in spots:
            builder.button(
                text=f"Место {spot.id}",
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
