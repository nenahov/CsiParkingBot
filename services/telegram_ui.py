"""Единый слой отправки обычных, rich и ephemeral-сообщений.

Telegram различает обычные сообщения в группе и ephemeral-ответы, видимые
только пользователю, который инициировал действие.  Вся работа с этим
различием собрана здесь, чтобы обработчики не дублировали условия для
Message/CallbackQuery и не пытались редактировать ephemeral-сообщения через
обычный editMessageText.
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    EphemeralMessageParameters,
    InputRichMessage,
    Message,
)

logger = logging.getLogger(__name__)


def event_message(event: Message | CallbackQuery) -> Message | None:
    """Вернуть сообщение, с которым работает событие."""

    if isinstance(event, CallbackQuery):
        return event.message if isinstance(event.message, Message) else None
    return event


def event_user(event: Message | CallbackQuery):
    return event.from_user


def is_private_message(message: Message | None) -> bool:
    return bool(message and message.chat.type == "private")


def is_ephemeral_message(message: Message | None) -> bool:
    if message is None:
        return False
    ephemeral_id = getattr(message, "ephemeral_message_id", None)
    return isinstance(ephemeral_id, int) and ephemeral_id != 0 and getattr(
        message, "receiver_user", None
    ) is not None


def ephemeral_parameters(
        event: Message | CallbackQuery,
        *,
        personal: bool,
) -> EphemeralMessageParameters | None:
    """Параметры personal-ответа в группе.

    В личном чате ephemeral-режим не нужен. Для callback сохраняем его id:
    Telegram может связать ephemeral-ответ с нажатой кнопкой.
    """

    message = event_message(event)
    if not personal or message is None or is_private_message(message):
        return None

    user = event_user(event)
    if user is None:
        return None

    return EphemeralMessageParameters(
        receiver_user_id=user.id,
        callback_query_id=event.id if isinstance(event, CallbackQuery) else None,
        replace_callback_query_message=False,
    )


def _formatted_kwargs(content: Any) -> dict[str, Any]:
    if hasattr(content, "as_kwargs"):
        return dict(content.as_kwargs())
    if isinstance(content, str):
        return {"text": content}
    raise TypeError(f"Unsupported Telegram content: {type(content)!r}")


def _is_feature_unsupported(error: TelegramBadRequest) -> bool:
    description = str(error).lower()
    feature_error = "ephemeral" in description or "rich" in description
    unsupported = any(
        marker in description
        for marker in ("unsupported", "not supported", "not allowed", "unknown field")
    )
    return feature_error and unsupported


def is_undeliverable_error(error: TelegramAPIError) -> bool:
    """Ошибки Telegram, означающие, что адресат недоступен."""

    description = str(error).lower()
    return any(marker in description for marker in (
        "user not found",
        "chat not found",
        "bot was blocked by the user",
        "user is deactivated",
    ))


async def send_message_if_reachable(bot, chat_id: int, **kwargs: Any) -> Any:
    """Не прерывать обработку, если отдельному адресату нельзя отправить сообщение."""

    try:
        return await bot.send_message(chat_id=chat_id, **kwargs)
    except TelegramAPIError as error:
        if not is_undeliverable_error(error):
            raise
        return None


async def answer(
        event: Message | CallbackQuery,
        *,
        personal: bool = False,
        **kwargs: Any,
) -> Any:
    """Отправить текстовый/форматированный ответ.

    Для personal-ответа в группе сначала пробуем ephemeral API. Если Telegram
    отверг такой ответ, отправляем его в личные сообщения пользователя, а не
    публикуем потенциально приватные данные в группе.
    """

    message = event_message(event)
    if message is None:
        return None

    params = ephemeral_parameters(event, personal=personal)
    send_kwargs = dict(kwargs)
    if params is not None:
        send_kwargs["ephemeral_message_parameters"] = params

    try:
        return await message.answer(**send_kwargs)
    except TelegramBadRequest as error:
        if is_undeliverable_error(error):
            return None
        if not _is_feature_unsupported(error):
            raise
        if params is None:
            raise
        user = event_user(event)
        if user is None:
            raise
        fallback = dict(kwargs)
        text = fallback.pop("text", None)
        if text is None:
            raise
        try:
            return await message.bot.send_message(
                chat_id=user.id,
                text=text,
                **fallback,
            )
        except TelegramAPIError:
            # Никогда не раскрывать personal-ответ в общем чате, даже если
            # Telegram не смог доставить его и в личку.
            return None


async def answer_content(
        event: Message | CallbackQuery,
        content: Any,
        *,
        personal: bool = False,
        **kwargs: Any,
) -> Any:
    """Отправить aiogram Text/formatting content через :func:`answer`."""

    send_kwargs = _formatted_kwargs(content)
    send_kwargs.update(kwargs)
    return await answer(event, personal=personal, **send_kwargs)


async def answer_rich(
        event: Message | CallbackQuery,
        rich_message: InputRichMessage,
        *,
        personal: bool = False,
        fallback_text: str | None = None,
        fallback_reply_markup: Any = None,
        **kwargs: Any,
) -> Any:
    """Отправить native rich-сообщение, при необходимости ephemeral."""

    message = event_message(event)
    if message is None:
        return None

    params = ephemeral_parameters(event, personal=personal)
    send_kwargs = dict(kwargs)
    if params is not None:
        send_kwargs["ephemeral_message_parameters"] = params

    try:
        return await message.answer_rich(rich_message, **send_kwargs)
    except TelegramBadRequest as error:
        if is_undeliverable_error(error):
            return None
        if not _is_feature_unsupported(error):
            raise
        if fallback_text is None:
            raise
        target_chat_id = message.chat.id
        if params is not None:
            user = event_user(event)
            if user is None:
                raise
            target_chat_id = user.id
        try:
            return await message.bot.send_message(
                chat_id=target_chat_id,
                text=fallback_text,
                reply_markup=fallback_reply_markup or kwargs.get("reply_markup"),
            )
        except TelegramAPIError:
            # Ошибка rich/ephemeral и недоступная личка — fail closed.
            logger.exception(
                "Не удалось отправить fallback rich-сообщения в чат %s",
                target_chat_id,
            )
            return None


async def edit(
        message: Message,
        *,
        personal: bool = False,
        **kwargs: Any,
) -> Any:
    """Изменить обычное или ephemeral-сообщение."""

    if is_ephemeral_message(message):
        allowed = {
            "text",
            "parse_mode",
            "entities",
            "link_preview_options",
            "reply_markup",
            "rich_message",
        }
        edit_kwargs = {key: value for key, value in kwargs.items() if key in allowed}
        return await message.bot.edit_ephemeral_message_text(
            chat_id=message.chat.id,
            receiver_user_id=message.receiver_user.id,
            ephemeral_message_id=message.ephemeral_message_id,
            **edit_kwargs,
        )

    return await message.edit_text(**kwargs)


async def edit_content(
        event: Message | CallbackQuery,
        content: Any,
        *,
        personal: bool = False,
        reply_markup: Any = None,
) -> Any:
    """Изменить сообщение либо отправить personal-ответ вместо public-сообщения."""

    message = event_message(event)
    if message is None:
        return None

    if personal and not is_private_message(message) and not is_ephemeral_message(message):
        return await answer_content(
            event,
            content,
            personal=True,
            reply_markup=reply_markup,
        )

    kwargs = _formatted_kwargs(content)
    kwargs["reply_markup"] = reply_markup
    return await edit(message, personal=personal, **kwargs)


async def edit_rich(
        event: Message | CallbackQuery,
        rich_message: InputRichMessage,
        *,
        personal: bool = False,
        fallback_text: str | None = None,
        fallback_reply_markup: Any = None,
        reply_markup: Any = None,
) -> Any:
    """Изменить rich-сообщение или создать personal-ответ в группе."""

    message = event_message(event)
    if message is None:
        return None

    if personal and not is_private_message(message) and not is_ephemeral_message(message):
        return await answer_rich(
            event,
            rich_message,
            personal=True,
            fallback_text=fallback_text,
            reply_markup=reply_markup,
            fallback_reply_markup=fallback_reply_markup,
        )

    kwargs: dict[str, Any] = {"rich_message": rich_message}
    if reply_markup is not None:
        kwargs["reply_markup"] = reply_markup
    try:
        return await edit(message, personal=personal, **kwargs)
    except TelegramBadRequest:
        if fallback_text is None:
            raise
        return await edit(
            message,
            personal=personal,
            text=fallback_text,
            reply_markup=fallback_reply_markup or reply_markup,
        )


async def send_private_notification(bot, chat_id: int, **kwargs: Any) -> Any:
    """Отправить durable-уведомление в личный чат пользователя."""

    return await send_message_if_reachable(bot, chat_id, **kwargs)
