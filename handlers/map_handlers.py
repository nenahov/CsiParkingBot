import json
from datetime import datetime
from io import BytesIO

from aiogram import Router, F
from aiogram.filters import Command, or_f
from aiogram.types import (
    Message,
    BufferedInputFile,
    CallbackQuery,
    InputMediaPhoto,
    InputRichMessage,
    InputRichBlockPhoto,
    InputRichBlockParagraph,
    RichMessageButton,
    RichTextButton,
)
from aiogram.utils.formatting import Text, Bold, Code
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.driver_callback import add_button, MyCallback
from models.driver import Driver
from services.notification_sender import send_alarm
from services.param_service import ParamService
from services.parking_service import ParkingService
from services.queue_service import QueueService
from utils.map_generator import generate_parking_map

router = Router()


@router.message(or_f(Command("map"), F.text.regexp(r"(?i)(.*пока.* (схем|карт)(а|у))|(.*(схем|карт)(а|у) парковки)")),
                flags={"long_operation": "upload_photo", "check_driver": True})
async def map_command(message: Message, session, driver, current_day, is_private):
    frame_index = await get_frame_index(message, session)
    rich_message, builder = await build_map_message(session, driver, current_day, is_private, frame_index)
    await message.answer_rich(rich_message=rich_message, reply_markup=builder.as_markup())


@router.callback_query(MyCallback.filter(F.action == "refresh-map"),
                       flags={"long_operation": "upload_photo", "check_driver": True})
async def refresh_map(callback: CallbackQuery, callback_data: MyCallback, session, driver, current_day, is_private):
    if current_day.toordinal() != callback_data.day_num:
        await send_alarm(callback, "Древняя карта, обновить не удастся 🏛️")
        return
    await callback.answer()
    rich_message, builder = await build_map_message(
        session, driver, current_day, is_private, callback_data.spot_id,
        numbers_on_top=bool(callback_data.bool_value),
    )
    await callback.message.edit_text(rich_message=rich_message, reply_markup=builder.as_markup())


async def build_map_message(session, driver, current_day, is_private, frame_index, numbers_on_top=False):
    parking_service = ParkingService(session)
    spots, reservations = await parking_service.get_spots_with_reservations(current_day)
    for spot in spots:
        await session.refresh(spot, ["current_driver"])
    queue_all = await QueueService(session).get_all()
    img = await generate_parking_map(
        parking_spots=spots,
        reservations_data=reservations,
        driver=driver if is_private else None,
        frame_index=frame_index,
        day=current_day,
        queue=queue_all,
        numbers_on_top=numbers_on_top,
    )

    img_buffer = BytesIO()
    img.save(img_buffer, format="PNG")

    builder = InlineKeyboardBuilder()
    if is_private:
        add_button("📅 Расписание...", "edit-schedule", driver.chat_id, builder)

    refresh_button = RichTextButton(
        button=RichMessageButton(
            text="Обновить",
            callback_data=MyCallback(action="refresh-map", user_id=0, spot_id=frame_index,
                                     day_num=current_day.toordinal(), event_type=None,
                                     bool_value=True if numbers_on_top else False).pack(),
            style="link",
        )
    )
    numbers_button = RichTextButton(
        button=RichMessageButton(
            text="Номера под машинами" if numbers_on_top else "Номера поверх машин",
            callback_data=MyCallback(action="refresh-map", user_id=0, spot_id=frame_index,
                                     day_num=current_day.toordinal(), event_type=None,
                                     bool_value=not numbers_on_top).pack(),
            style="link",
        )
    )

    legend = ("🔴 - забронировано\n"
              f"{'🟡 - забронировано Вами\n' if is_private else ''}"
              "🟢 - свободно")
    queue_text = (f"Всего в очереди: {len(queue_all)} человек(а)\n"
                  f"{''.join(f'• {queue.driver.description}{(" ❗️🏆 ❗️ " + str(queue.spot_id) + " место до " + queue.choose_before.strftime('%H:%M')) if queue.spot_id else ''}\n' for queue in queue_all)}")

    rich_message = InputRichMessage(
        blocks=[
            InputRichBlockPhoto(
                photo=InputMediaPhoto(media=BufferedInputFile(img_buffer.getvalue(), filename="map.png")),
            ),
            InputRichBlockParagraph(text=f"Карта парковки на {current_day.strftime('%a %d.%m.%Y')}."),
            InputRichBlockParagraph(text=[
                f"(Обновлено {datetime.now().strftime('%d.%m.%Y %H:%M')}) ",
                refresh_button,
                " · ",
                numbers_button,
            ]),
            InputRichBlockParagraph(text=legend),
            InputRichBlockParagraph(text=queue_text.rstrip("\n")),
        ]
    )
    return rich_message, builder


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
