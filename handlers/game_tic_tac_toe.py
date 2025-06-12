import base64
from typing import List, Tuple

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


class GomokuAI:
    # Directions: horizontal, vertical, diag1, diag2
    DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]

    # Score table: (chain length, open ends) -> score
    SCORE_TABLE = {
        (5, 0): 100000,
        (5, 1): 100000,
        (5, 2): 100000,
        (4, 2): 10000,  # open four
        (4, 1): 1000,  # closed four
        (3, 2): 1000,  # open three
        (3, 1): 100,  # closed three
        (2, 2): 100,  # open two
        (2, 1): 10,  # closed two
        (1, 2): 10,  # isolated stone
    }

    @staticmethod
    def in_bounds(x: int, y: int, rows: int, cols: int) -> bool:
        return 0 <= x < rows and 0 <= y < cols

    @classmethod
    def evaluate_position(cls, field: List[List[int]], x: int, y: int, player: int) -> int:
        """Evaluate heuristic score for placing `player` at (x,y)."""
        rows, cols = len(field), len(field[0])
        total_score = 0

        for dx, dy in cls.DIRECTIONS:
            count = 1  # including this new move
            open_ends = 0

            # count in positive direction
            i, j = x + dx, y + dy
            while cls.in_bounds(i, j, rows, cols) and field[i][j] == player:
                count += 1
                i += dx
                j += dy
            # check open end
            if cls.in_bounds(i, j, rows, cols) and field[i][j] == 0:
                open_ends += 1

            # count in negative direction
            i, j = x - dx, y - dy
            while cls.in_bounds(i, j, rows, cols) and field[i][j] == player:
                count += 1
                i -= dx
                j -= dy
            # check other open end
            if cls.in_bounds(i, j, rows, cols) and field[i][j] == 0:
                open_ends += 1

            # cap count at 5
            count = min(count, 5)
            # get score
            total_score += cls.SCORE_TABLE.get((count, open_ends), 0)

        return total_score

    @classmethod
    def get_best_move(cls, field: List[List[int]]) -> Tuple[int, int]:
        """Return best move (row, col) for player 2 based on heuristic evaluation."""
        best_move = (-1, -1)
        best_score = float('-inf')
        rows, cols = len(field), len(field[0])

        for i in range(rows):
            for j in range(cols):
                if field[i][j] != 0:
                    continue

                # evaluate for AI (player 2)
                score_ai = cls.evaluate_position(field, i, j, player=2)
                # evaluate for opponent (player 1) to block
                score_op = cls.evaluate_position(field, i, j, player=1)
                # combined score: favor own moves, but block opponent threats
                score = score_ai + score_op * 0.9

                if score > best_score:
                    best_score = score
                    best_move = (i, j)

        return best_move


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
                win_line: list[tuple[int, int]] | None = None,
                is_private=False) -> InlineKeyboardBuilder:
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
            data = f"XO|{i}{j}|{state_str}|{turn}|{p1},{p2}|{title}|{int(d1)},{int(d2)}"
            # если клетка занята или игра закончена, блокируем кнопку
            btn = InlineKeyboardButton(text=emoji, callback_data=data if (v == 0 and not is_end) else "pass")
            row.append(btn)
        kb.row(*row)

    if not is_private and count_move > 15:
        # Ничью предлагаем не сразу
        label = 'Ничья 🤝' if (d1 and d2) else ('Ничья ❓' if (d1 or d2) else 'Предложить ничью')
        draw_data = f"XO|D|{state_str}|{turn}|{p1},{p2}|{title}|{int(d1)},{int(d2)}"
        kb.row(InlineKeyboardButton(text=label, callback_data=draw_data if not is_end else "pass"))

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
    content = Bold(f"Крестики-нолики {w}×{h}, {WIN_LENGTH} в ряд.")
    content += f"\n{title[0]} ходит первым."
    await send_reply(message, content, kb)


@router.callback_query(F.data.startswith("XO|"), flags={"check_driver": True})
async def process_move(callback: types.CallbackQuery, driver: Driver, session: AsyncSession, is_private):
    data = callback.data
    # Разобрать данные
    _, pos, state_str, turn_str, players, title, draw, _ = (data + "|||||||").split('|', 7)
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
        if is_private:
            # Ход бота
            bi, bj = GomokuAI.get_best_move(field)
            current_move = (bi, bj)
            if bi >= 0:
                field[bi][bj] = 2
                if win_line := find_win_line(field, 2):
                    content = Text("Бот в этот раз сильнее...")
                else:
                    content = Text("Ваш ход!")
            else:
                content = Text("Что-то пошло не так!")
            next_turn = 1
            new_state = encode_field(field)
        else:
            content = Text("Ход ")
            content += get_player_title_url(title[0], player_1) if next_turn == 1 \
                else get_player_title_url(title[2], player_2)

    kb = build_board(field, new_state, next_turn, p1, p2, title, current_move, draw_offers, win_line, is_private)
    await send_reply(callback, content + vs, kb)
    await callback.answer()


def get_player_title(title: str, player: Driver):
    return f"{title} {player.description}" if player else title


def get_player_title_url(title: str, player: Driver):
    return Text(f"{title} ") + TextLink(player.title, url=f"tg://user?id={player.chat_id}") if player else Text(title)
