import base64

from aiogram import F, Router
from aiogram import types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton
from aiogram.utils.formatting import Bold, Text, TextLink
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from models.driver import Driver
from services.driver_service import DriverService
from services.notification_sender import send_reply, send_alarm

router = Router()

default_title = '🚗🚘🚕🚖'

w, h = (8, 10)
WIN_LENGTH = 5


# --- Encoding utilities -----------------------------------------------------
def encode_field(field: list[list[int]]) -> str:
    """
    Кодирует произвольное поле размера h×w (значения 0,1,2) в строку Base64.
    """
    # Свернуть все клетки в одно число в системе счисления base 3
    n = 0
    for row in field:
        for v in row:
            n = n * 3 + v
    # Перевести число в байты и закодировать base64 без паддинга
    byte_len = (n.bit_length() + 7) // 8
    b = n.to_bytes(byte_len, 'big') if byte_len > 0 else b'\x00'
    s = base64.urlsafe_b64encode(b).rstrip(b'=')
    return s.decode('ascii')


def decode_field(s: str) -> list[list[int]]:
    """
    Декодирует строку Base64 обратно в поле размера h×w.
    """
    # Восстановление паддинга и получение числа
    padding = '=' * ((4 - len(s) % 4) % 4)
    b = base64.urlsafe_b64decode(s + padding)
    n = int.from_bytes(b, 'big')
    # Восстановить массив цифр base 3 длины w*h
    total = w * h
    arr = [0] * total
    for i in range(total - 1, -1, -1):
        n, r = divmod(n, 3)
        arr[i] = r
    # Сформировать список списков
    return [arr[i * w:(i + 1) * w] for i in range(h)]


# --- Game logic --------------------------------------------------------------
def find_win_line(field: list[list[int]], symbol: int) -> list[tuple[int, int]] | None:
    directions = [(1, 0), (0, 1), (1, 1), (1, -1)]
    for i in range(h):
        for j in range(w):
            if field[i][j] != symbol:
                continue
            for di, dj in directions:
                line = []
                x, y = i, j
                while 0 <= x < h and 0 <= y < w and field[x][y] == symbol:
                    line.append((x, y))
                    if len(line) == WIN_LENGTH:
                        return line
                    x += di
                    y += dj
    return None


# --- Inline keyboard builder ------------------------------------------------
def build_board(field: list[list[int]], state_str: str, turn: int, p1: int, p2: int, title: str,
                current_move: tuple[int, int] | None = None,
                draw_offers: tuple[bool, bool] = (False, False),
                win_line: list[tuple[int, int]] | None = None) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    d1, d2 = draw_offers
    is_end = (d1 and d2) or win_line
    count_move = 0
    for i in range(h):
        row = []
        for j in range(w):
            v = field[i][j]
            if v != 0:
                count_move += 1
            if (win_line and (i, j) in win_line) or (current_move and i == current_move[0] and j == current_move[1]):
                # выделяем символами победителя
                emoji = title[1] if v == 1 else title[3]
            else:
                emoji = '➖' if v == 0 else (title[0] if v == 1 else title[2])
            data = f"{i}{j}|{state_str}|{turn}|{p1},{p2}|{title}|{int(d1)},{int(d2)}"
            # если клетка занята или игра закончена, блокируем кнопку
            btn = InlineKeyboardButton(text=emoji, callback_data=data if (v == 0 and not is_end) else "IGNORE")
            row.append(btn)
        kb.row(*row)

    if count_move > 15:
        # Ничью предлагаем не сразу
        label = 'Ничья 🤝' if (d1 and d2) else ('Ничья ❓' if (d1 or d2) else 'Предложить ничью')
        draw_data = f"D|{state_str}|{turn}|{p1},{p2}|{title}|{int(d1)},{int(d2)}"
        kb.row(InlineKeyboardButton(text=label, callback_data=draw_data if not is_end else "IGNORE"))

    return kb


# --- Handlers ----------------------------------------------------------------
@router.message(Command("XO"), flags={"check_driver": True})
async def cmd_start(message: types.Message):
    # Ожидаем команду: /XO xXoO
    split = message.text.split()
    if len(split) > 1 and len(split[1]) == 4:
        title = split[1]
    else:
        title = default_title
    p1 = 0
    p2 = 0
    # Инициализировать пустое поле
    field = [[0] * w for _ in range(h)]
    state_str = encode_field(field)
    turn = 1  # 1 = X, 2 = O
    kb = build_board(field, state_str, turn, p1, p2, title)
    content = Bold(f"Крестики-нолики {w}×{h}, {WIN_LENGTH} в ряд.)")
    content += f"\n{title[0]} ходит первым."
    await send_reply(message, content, kb)


@router.callback_query(F.data, flags={"check_driver": True})
async def process_move(callback: types.CallbackQuery, driver: Driver, session: AsyncSession):
    data = callback.data
    if data == "IGNORE":
        await callback.answer()
        return
    # Разобрать данные
    pos, state_str, turn_str, players, title, draw, _ = (data + "|||||||").split('|', 6)
    if not title or len(title) != 4:
        title = default_title
    if not draw:
        draw_offers = (False, False)
    else:
        d1, d2 = map(int, draw.split(','))
        draw_offers = (bool(d1), bool(d2))
    turn = int(turn_str)
    p1, p2 = map(int, players.split(','))
    # Проверяем, чей ход
    user_id = driver.id
    if turn == 1:
        if p1 == 0 and p2 != user_id:
            p1 = user_id
        expected = p1
    else:
        if p2 == 0 and p1 != user_id:
            p2 = user_id
        expected = p2

    current_move = (-1, -1)
    if pos == 'D':
        # Предложить ничью
        if turn == 1:
            if p1 == user_id:
                draw_offers = (not draw_offers[0], draw_offers[1])
            elif p2 == user_id:
                draw_offers = (draw_offers[0], not draw_offers[1])
            else:
                await send_alarm(callback, "Не Ваша игра!")
                return
        else:
            if p2 == user_id:
                draw_offers = (draw_offers[0], not draw_offers[1])
            elif p1 == user_id:
                draw_offers = (not draw_offers[0], draw_offers[1])
            else:
                await send_alarm(callback, "Не Ваша игра!")
                return

    if user_id != expected:
        await send_alarm(callback, "Не Ваш ход!")
        return

    next_turn = turn
    new_state = state_str
    # Восстанавливаем поле и делаем ход
    field = decode_field(state_str)
    if pos != 'D':
        i, j = int(pos[0]), int(pos[1])
        if field[i][j] != 0:
            await callback.answer()
            return
        field[i][j] = turn
        current_move = (i, j)
        next_turn = 2 if turn == 1 else 1
        new_state = encode_field(field)

    driver_service = DriverService(session)
    player_1 = await driver_service.get_by_id(p1) if p1 != 0 else None
    player_2 = await driver_service.get_by_id(p2) if p2 != 0 else None
    vs = Bold(f"\n\n{get_player_title(title[0], player_1)} vs {get_player_title(title[2], player_2)}")
    # Проверяем победу
    win_line = find_win_line(field, turn)
    if win_line:
        content = Text(
            f"Игрок {get_player_title(title[0], player_1) if turn == 1 else get_player_title(title[2], player_2)} выиграл!")
    elif draw_offers[0] and draw_offers[1]:
        content = Text("Ничья!")
    else:
        content = Text("Ход ")
        content += get_player_title_url(title[0], player_1) if next_turn == 1 \
            else get_player_title_url(title[2], player_2)

    kb = build_board(field, new_state, next_turn, p1, p2, title, current_move, draw_offers, win_line)
    await send_reply(callback, content + vs, kb)
    await callback.answer()


def get_player_title(title: str, player: Driver):
    return f"{title} {player.description}" if player else title


def get_player_title_url(title: str, player: Driver):
    return Text(f"{title} ") + TextLink(player.title, url=f"tg://user?id={player.chat_id}") if player else Text(title)
