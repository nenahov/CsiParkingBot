import asyncio
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.dispatcher.flags import get_flag
from aiogram.types import TelegramObject

shared_locks = dict()


class LockOperationMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any],
    ) -> Any:
        lock_name = get_flag(data, "lock_operation")

        # Если такого флага на хэндлере нет
        if not lock_name:
            return await handler(event, data)

        # Если флаг есть
        shared_lock = shared_locks.setdefault(lock_name, asyncio.Lock())
        async with shared_lock:
            return await handler(event, data)
