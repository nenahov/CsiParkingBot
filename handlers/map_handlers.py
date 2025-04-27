import json
from datetime import datetime, timedelta
from io import BytesIO

from aiogram import Router, F
from aiogram.filters import Command, or_f
from aiogram.types import Message, BufferedInputFile, CallbackQuery
from aiogram.utils.formatting import Text, Bold, Code
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.driver_callback import add_button, MyCallback
from models.driver import Driver
from services.param_service import ParamService
from services.parking_service import ParkingService
from services.queue_service import QueueService
from utils.map_generator import generate_parking_map

router = Router()


@router.message(F.text.regexp(r"(?i)(.*пока.* карт(а|у) на завтра)|(.*карт(а|у) парковки на завтра)"),
                flags={"long_operation": "upload_photo", "check_driver": True})
async def map_tomorrow_command(message: Message, session, driver, current_day, is_private):
    day = current_day + timedelta(days=1)

    # Получаем данные для карты
    parking_service = ParkingService(session)
    spots, reservations = await parking_service.get_spots_with_reservations(day)
    frame_index = await get_frame_index(message, session)

    # Генерируем карту
    img = await generate_parking_map(parking_spots=spots, reservations_data=reservations,
                               driver=driver if is_private else None,
                                     use_spot_status=False, frame_index=frame_index,
                                     day=day
                                     )

    img_buffer = BytesIO()
    img.save(img_buffer, format="PNG")
    img_buffer.seek(0)

    # Отправка изображения
    await message.answer_photo(
        BufferedInputFile(img_buffer.getvalue(), filename="map.png"),
        caption=f"Карта парковки на завтра {day.strftime('%a %d.%m.%Y')}\n\n"
                f"🔴 - забронировано\n"
                f"{'🟡 - забронировано Вами\n' if is_private else ''}"
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
    frame_index = await get_frame_index(message, session)
    for spot in spots:
        await session.refresh(spot, ["current_driver"])
    # Генерируем карту
    img = await generate_parking_map(
        parking_spots=spots,
        reservations_data=reservations,
        driver=driver if is_private else None,
        frame_index=frame_index,
        day=current_day
    )

    img_buffer = BytesIO()
    img.save(img_buffer, format="PNG")
    img_buffer.seek(0)

    builder = InlineKeyboardBuilder()
    if is_private:
        add_button("📅 Расписание...", "edit-schedule", driver.chat_id, builder)

    queue_service = QueueService(session)
    queue_all = await queue_service.get_all()

    # Отправка изображения
    await message.answer_photo(
        BufferedInputFile(img_buffer.getvalue(), filename="map.png"),
        caption=f"Карта парковки на {current_day.strftime('%a %d.%m.%Y')}.\n"
                f"(Обновлено {datetime.now().strftime('%d.%m.%Y %H:%M')})\n\n"
                f"🔴 - забронировано\n"
                f"{'🟡 - забронировано Вами\n' if is_private else ''}"
                f"🟢 - свободно\n\n"
                f"Всего в очереди: {len(queue_all)} человек(а)\n"
        # Список позиций и водителей в очереди
                f"{''.join(f'• {queue.driver.description}{(" ❗️🏆 ❗️ " + str(queue.spot_id) + " место до " + queue.choose_before.strftime('%H:%M')) if queue.spot_id else ''}\n' for queue in queue_all)}",
        reply_markup=builder.as_markup()
    )


async def get_frame_index(message, session):
    param_service = ParamService(session)
    chat_id = message.chat.id
    frames_json = await param_service.get_parameter("map_frame_index", '{}')
    frames = json.loads(frames_json)
    frame_index = frames.get(str(chat_id), -1) + 1
    frames[str(chat_id)] = frame_index
    await param_service.set_parameter("map_frame_index", json.dumps(frames))
    return frame_index


@router.callback_query(MyCallback.filter(F.action == "edit-schedule"),
                       flags={"check_driver": True, "check_callback": True})
async def handle_spot_selection(callback: CallbackQuery, session, driver):
    await spot_selection(callback.message, session, driver, True)
    await callback.answer()


@router.callback_query(MyCallback.filter(F.action == "choose-spots"),
                       flags={"check_driver": True, "check_callback": True})
async def handle_spot_selection(callback: CallbackQuery, session, driver):
    await spot_selection(callback.message, session, driver, False)


async def spot_selection(message: Message, session, driver: Driver, is_new: bool):
    # Добавляем кнопки выбора мест
    builder = InlineKeyboardBuilder()
    # Получаем данные для карты
    await session.refresh(driver, ["reservations", "parking_spots"])
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
        add_button(f"{spot.id}", "select-spot", driver.chat_id, builder, spot.id)
    builder.adjust(3)

    reservations = driver.reservations

    content = Text(
        "📅 Тут вы можете забронировать парковку по дням недели.\n\n",
        Text(*[
            elem for day, num in [
                ("Пн", 0), ("Вт", 1), ("Ср", 2),
                ("Чт", 3), ("Пт", 4), ("Сб", 5), ("Вс", 6)
            ]
            for elem in (
                Code(
                    f"{day}\t..\t" + (
                        ', '.join(f"{res.parking_spot_id}"
                                  for res in reservations
                                  if res.day_of_week == num)
                        if any(res.day_of_week == num for res in reservations)
                        else "у Вас нет бронирования"
                    )
                ),
                "\n"
            )
        ]),
        Bold("\nВыберите место для бронирования:"))

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
