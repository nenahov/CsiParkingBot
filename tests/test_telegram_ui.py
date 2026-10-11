import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendRichMessage
from aiogram.types import (
    CallbackQuery,
    Chat,
    EphemeralMessageParameters,
    InputRichBlockButtons,
    InputRichBlockParagraph,
    InputRichMessage,
    Message,
    User,
)

from handlers.user_handlers import get_status_rich_message
from services.telegram_ui import (
    _is_feature_unsupported,
    answer_rich,
    ephemeral_parameters,
    edit_content,
    edit,
)


def make_message(chat_type="group", bot=None):
    user = User.model_construct(id=42, is_bot=False, first_name="Alex")
    chat = Chat.model_construct(
        id=-100123 if chat_type != "private" else 42,
        type=chat_type,
    )
    return Message.model_construct(chat=chat, from_user=user, _bot=bot)


class TelegramUiTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_rich_message_does_not_duplicate_inline_actions(self):
        session = AsyncMock()
        driver = type(
            "DriverStub",
            (),
            {
                "chat_id": 42,
                "title": "Алекс",
                "description": "Водитель",
                "absent_until": None,
                "attributes": {},
                "is_absent": lambda self, _: False,
                "get_occupied_spots": lambda self: [],
                "my_spots": lambda self: [],
                "get_karma": lambda self: 5,
            },
        )()

        with patch(
                "handlers.user_handlers.ParkingService"
        ) as parking_service, patch(
            "handlers.user_handlers.QueueService"
        ) as queue_service:
            parking_service.return_value.get_spots_with_reservations = AsyncMock(
                return_value=([], [])
            )
            queue_service.return_value.is_driver_in_queue = AsyncMock(
                return_value=False
            )

            rich_message, _ = await get_status_rich_message(
                driver, session, date(2026, 10, 12)
            )

        self.assertFalse(
            any(isinstance(block, InputRichBlockButtons) for block in rich_message.blocks)
        )

    def test_ephemeral_parameters_are_only_created_for_group_personal_replies(self):
        group_message = make_message()
        params = ephemeral_parameters(group_message, personal=True)
        self.assertIsInstance(params, EphemeralMessageParameters)
        self.assertEqual(params.receiver_user_id, 42)

        private_message = make_message("private")
        self.assertIsNone(ephemeral_parameters(private_message, personal=True))
        self.assertIsNone(ephemeral_parameters(group_message, personal=False))

    def test_callback_ephemeral_parameters_include_callback_context(self):
        message = make_message()
        callback = CallbackQuery.model_construct(
            id="callback-123",
            from_user=message.from_user,
            message=message,
            chat_instance="group-instance",
        )
        params = ephemeral_parameters(callback, personal=True)
        self.assertEqual(params.receiver_user_id, 42)
        self.assertEqual(params.callback_query_id, "callback-123")

    def test_only_explicit_rich_ephemeral_unsupported_errors_are_fallback_candidates(self):
        rich_method = SendRichMessage(
            chat_id=-100123,
            rich_message=InputRichMessage(
                blocks=[InputRichBlockParagraph(text="private")]
            ),
        )
        self.assertTrue(
            _is_feature_unsupported(
                TelegramBadRequest(method=rich_method, message="Rich messages are not supported")
            )
        )
        self.assertFalse(
            _is_feature_unsupported(
                TelegramBadRequest(method=rich_method, message="message is too long")
            )
        )

    async def test_non_feature_bad_request_does_not_retry_or_leak(self):
        bot = AsyncMock()
        message = make_message(bot=bot)
        rich = InputRichMessage(blocks=[InputRichBlockParagraph(text="Private status")])
        error = TelegramBadRequest(
            method=SendRichMessage(chat_id=-100123, rich_message=rich),
            message="message is too long",
        )
        with patch.object(Message, "answer_rich", new_callable=AsyncMock, side_effect=error):
            with self.assertRaises(TelegramBadRequest):
                await answer_rich(
                    message,
                    rich,
                    personal=True,
                    fallback_text="Private status",
                )
        bot.send_message.assert_not_awaited()

    async def test_private_chat_does_not_receive_ephemeral_parameters(self):
        message = make_message("private")
        rich = InputRichMessage(blocks=[InputRichBlockParagraph(text="Status")])
        with patch.object(
                Message,
                "answer_rich",
                new_callable=AsyncMock,
                return_value="sent",
        ) as send:
            result = await answer_rich(message, rich, personal=True, fallback_text="Status")
        self.assertEqual(result, "sent")
        self.assertNotIn("ephemeral_message_parameters", send.await_args.kwargs)

    async def test_unsupported_ephemeral_rich_falls_back_to_dm_not_group(self):
        bot = AsyncMock()
        message = make_message(bot=bot)
        rich = InputRichMessage(blocks=[InputRichBlockParagraph(text="Private status")])
        error = TelegramBadRequest(
            method=SendRichMessage(
                chat_id=-100123,
                rich_message=rich,
                ephemeral_message_parameters=EphemeralMessageParameters(receiver_user_id=42),
            ),
            message="Ephemeral rich messages are not supported",
        )
        with patch.object(Message, "answer_rich", new_callable=AsyncMock, side_effect=error):
            await answer_rich(
                message,
                rich,
                personal=True,
                fallback_text="Private status",
            )
        bot.send_message.assert_awaited_once()
        self.assertEqual(bot.send_message.await_args.kwargs["chat_id"], 42)
        self.assertEqual(bot.send_message.await_args.kwargs["text"], "Private status")

    async def test_personal_edit_of_legacy_group_message_creates_ephemeral_reply(self):
        message = make_message()
        callback = CallbackQuery.model_construct(
            id="callback-456",
            from_user=message.from_user,
            message=message,
            chat_instance="group-instance",
        )
        with patch.object(
                Message,
                "answer",
                new_callable=AsyncMock,
                return_value="ephemeral reply",
        ) as send, patch.object(
            Message,
            "edit_text",
            new_callable=AsyncMock,
        ) as edit_public:
            result = await edit_content(callback, "Private details", personal=True)

        self.assertEqual(result, "ephemeral reply")
        self.assertEqual(send.await_args.kwargs["text"], "Private details")
        self.assertEqual(
            send.await_args.kwargs["ephemeral_message_parameters"].receiver_user_id,
            42,
        )
        edit_public.assert_not_awaited()

    async def test_ephemeral_message_edit_uses_ephemeral_bot_method(self):
        bot = AsyncMock()
        message = Message.model_construct(
            chat=Chat.model_construct(id=-100123, type="group"),
            from_user=User.model_construct(id=42, is_bot=False, first_name="Alex"),
            ephemeral_message_id=987,
            receiver_user=User.model_construct(id=42, is_bot=False, first_name="Alex"),
            _bot=bot,
        )

        await edit(message, text="Updated private status")

        bot.edit_ephemeral_message_text.assert_awaited_once_with(
            chat_id=-100123,
            receiver_user_id=42,
            ephemeral_message_id=987,
            text="Updated private status",
        )


if __name__ == "__main__":
    unittest.main()
