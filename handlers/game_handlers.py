import asyncio
import logging
import random

from aiogram import types, F, Router
from aiogram.filters import Command
from aiogram.filters import or_f
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from models.driver import Driver
from services.param_service import ParamService

router = Router()
games = {}
hi_score = -1


async def get_hi_score(session):
    global hi_score
    if hi_score < 0:
        param_service = ParamService(session)
        hi_score = int(await param_service.get_parameter("hi_score", "0"))
    return hi_score


class GameState:
    def __init__(self, chat_id, message_id):
        self.bot = None
        self.chat_id = chat_id
        self.message_id = message_id
        self.player_name = 'Игрок'
        self.road_width = 9
        self.visible_lines = 19
        self.player_pos = 4
        self.car_width = 3
        self.car_height = 4
        self.score = 0
        self.is_active = True
        self.frame_count = 0
        self.enemies = []
        self.border = '▣'
        self.update_task = None

        self.player_car = [
            ['▢', '▣', '▢'],
            ['▣', '▣', '▣'],
            ['▢', '▣', '▢'],
            ['▣', '▢', '▣']
        ]

        self.enemy_cars = [
            [
                ['▢', '▣', '▢'],
                ['▣', '▣', '▣'],
                ['▢', '▣', '▢'],
                ['▣', '▢', '▣']
            ],
            [
                ['▢', '▣', '▢'],
                ['▣', '▣', '▣'],
                ['▢', '▣', '▢'],
                ['▣', '▢', '▣']
            ]
        ]

    async def start_auto_update(self, bot, session: AsyncSession):
        """Запуск автоматического обновления"""
        self.bot = bot
        self.update_task = asyncio.create_task(self.auto_update(session))

    async def auto_update(self, session: AsyncSession):
        """Автоматическое обновление игры"""
        while self.is_active:
            await asyncio.sleep(2.5)
            self.update()
            if self.is_active:
                await self.redraw(session)
            else:
                await self.game_over(session)

    async def redraw(self, session: AsyncSession):
        """Перерисовка игрового поля"""
        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=self.message_id,
                text=await self.draw(session),
                reply_markup=await get_controls()
            )
        except Exception as e:
            logging.error(f"Error redrawing: {e}")

    async def game_over(self, session: AsyncSession):
        """Обработка завершения игры"""
        global hi_score
        hi_score = await get_hi_score(session)
        if self.score > hi_score:
            hi_score = self.score
            param_service = ParamService(session)
            await param_service.set_parameter("hi_score", str(hi_score))
        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=self.message_id,
                text=f"💥 БУМ! FINAL SCORE: {self.score}\n{await self.draw(session)}"
            )
        except Exception as e:
            logging.error(f"Error in game over: {e}")

    def move_player(self, direction):
        if not self.is_active:
            return
        new_pos = self.player_pos + direction
        if 0 <= new_pos <= self.road_width - self.car_width:
            self.player_pos = new_pos

    def update(self):
        if not self.is_active:
            return

        self.frame_count += 1
        self.score += 10

        # Обновление позиций врагов
        for enemy in self.enemies:
            enemy['y'] += 0.5
            if self.check_collision(enemy):
                self.is_active = False
                return

        # Генерация новых врагов с проверкой коллизий
        if self.frame_count % 20 == 0:
            self.try_spawn_enemy()

        # Удаление вышедших за пределы врагов
        self.enemies = [e for e in self.enemies if e['y'] < self.visible_lines + 4]

    def try_spawn_enemy(self):
        """Попытка создать врага с проверкой свободного места"""
        for _ in range(5):  # Максимум 5 попыток
            x = random.randint(1, self.road_width - self.car_width)
            new_enemy = {
                'x': x,
                'y': -4,
                'pattern': random.choice(self.enemy_cars)
            }

            # Проверка коллизий с существующими врагами
            if not any(self.enemy_collision(new_enemy, e) for e in self.enemies):
                self.enemies.append(new_enemy)
                return

    def enemy_collision(self, e1, e2):
        """Проверка коллизий между врагами"""
        return not (
                e1['x'] >= e2['x'] + self.car_width or
                e1['x'] + self.car_width <= e2['x'] or
                e1['y'] >= e2['y'] + self.car_height or
                e1['y'] + self.car_height <= e2['y']
        )

    def check_collision(self, enemy):
        """Проверка столкновения с игроком"""
        player_rect = (self.player_pos, self.visible_lines - 4)
        enemy_rect = (enemy['x'], enemy['y'])

        return not (
                player_rect[0] >= enemy_rect[0] + self.car_width or
                player_rect[0] + self.car_width <= enemy_rect[0] or
                player_rect[1] >= enemy_rect[1] + self.car_height or
                player_rect[1] + self.car_height <= enemy_rect[1]
        )

    async def draw(self, session: AsyncSession):
        buffer = [f"🏁 За рулем {self.player_name}\n"]

        # buffer.append(f"🏁 SCORE: {self.score:06d} 🏁\n🏁 HI: {hi_score:06d} 🏆\n")

        bi = self.score / 10
        for line_num in range(self.visible_lines):
            bi += 1
            add = ""
            if line_num == 2:
                add = "     SCORE"
            if line_num == 3:
                add = f"    {self.score:06d}"
            if line_num == 5:
                add = "  HI-SCORE"
            if line_num == 6:
                hi_score = await get_hi_score(session)
                add = f"    {hi_score :06d}"
            line = list(self.border + '▢' * self.road_width + self.border + add) if bi % 3 != 0 else list(
                '▢' * (self.road_width + 2) + add)

            # Отрисовка врагов
            for enemy in self.enemies:
                if 0 <= line_num - enemy['y'] < 4:
                    part = enemy['pattern'][int(line_num - enemy['y'])]
                    for dx in range(3):
                        pos = 1 + enemy['x'] + dx
                        if 1 <= pos < len(line) - 1:
                            line[pos] = part[dx]

            # Отрисовка игрока
            if line_num >= self.visible_lines - 4:
                part = self.player_car[line_num - (self.visible_lines - 4)]
                for dx in range(3):
                    pos = 1 + self.player_pos + dx
                    if 1 <= pos < len(line) - 1:
                        line[pos] = part[dx]

            buffer.append(''.join(line) + '\n')

        return ''.join(buffer)


@router.message(or_f(Command("tetris"), F.text.regexp(r"(?i)(.*тетрис)")),
                flags={"check_driver": True})
async def start_game(message: types.Message, driver: Driver, session: AsyncSession):
    game_id = message.chat.id

    # Удаляем предыдущую игру если существует
    if game_id in games:
        games[game_id].is_active = False
        del games[game_id]

    # Создаем новую игру
    msg = await message.answer("🚀 Поехали!\n\nИспользуй ⬅️ / ➡️,\nчтобы объезжать препятствия")
    game = GameState(message.chat.id, msg.message_id)
    game.player_name = driver.title
    games[game_id] = game
    await game.start_auto_update(message.bot, session)


@router.callback_query(lambda c: c.data in ['game_left', 'game_right'], flags={"check_driver": True})
async def handle_move(callback: types.CallbackQuery, driver: Driver):
    game_id = callback.message.chat.id
    if game_id not in games:
        await callback.answer("Начните игру с помощью команды /tetris")
        return

    game = games[game_id]
    if not game.is_active:
        await callback.answer("Game over! Начните игру с помощью команды /tetris")
        return

    game.player_name = driver.title
    direction = -1 if callback.data == 'game_left' else 1
    game.move_player(direction)
    await callback.answer()


# answer = text(f"▢▢▢▢▢▢▢▢▢▢\n"
#               f"▣▢▢▢▢▢▢▢▢▣\n"
#               f"▣▢▣▢▢▢▢▢▢▣{code("    SCORE")}\n"
#               f"▢▣▣▣▢▢▢▢▢▢{code("   000800")}\n"
#               f"▣▢▣▢▢▢▢▢▢▣\n"
#               f"▣▣▢▣▢▢▢▢▢▣{code(" HI-SCORE")}\n"
#               f"▢▢▢▢▢▢▢▢▢▢{code("   000970")}\n"
#               f"▣▢▢▢▢▢▢▢▢▣\n"
#               f"▣▢▢▢▢▢▢▢▢▣\n"
#               f"▢▢▢▢▢▢▢▢▢▢\n"
#               f"▣▢▢▢▢▢▣▢▢▣\n"
#               f"▣▢▢▢▢▣▣▣▢▣\n"
#               f"▢▢▢▢▢▢▣▢▢▢\n"
#               f"▣▢▢▢▢▣▢▣▢▣\n"
#               f"▣▢▢▢▢▢▢▢▢▣\n"
#               f"▢▢▢▢▢▢▢▢▢▢\n"
#               f"▣▢▢▢▣▢▢▢▢▣\n"
#               f"▣▢▢▣▣▣▢▢▢▣\n"
#               f"▢▢▢▢▣▢▢▢▢▢\n"
#               f"▣▢▢▣▢▣▢▢▢▣\n")
# print(answer)
# await message.answer(answer, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=builder.as_markup())


async def get_controls() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="⬅️", callback_data='game_left'))
    builder.add(InlineKeyboardButton(text="➡️", callback_data='game_right'))
    builder.adjust(2)
    return builder.as_markup()
