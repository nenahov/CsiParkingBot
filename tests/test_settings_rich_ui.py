import importlib
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.types import InputRichBlockButtons, InputRichBlockTable, RichTextButton

from handlers.driver_callback import MyCallback
from services.notification_sender import EventType


def load_edit_alarms():
    """Load settings UI without importing its unrelated image-carousel stack."""
    carousel_stub = types.ModuleType("utils.cars_generator")
    carousel_stub.generate_carousel_image = lambda *args, **kwargs: None
    carousel_stub.cars_count = 0
    carousel_stub.extra_cars_count = 0
    with patch.dict(sys.modules, {"utils.cars_generator": carousel_stub}):
        return importlib.import_module("handlers.settings_handlers").edit_alarms


class SettingsRichUiTests(unittest.IsolatedAsyncioTestCase):
    async def test_notification_settings_use_rich_actions_with_legacy_fallback(self):
        edit_alarms = load_edit_alarms()
        event = SimpleNamespace(
            message=SimpleNamespace(chat=SimpleNamespace(type="private"))
        )
        driver = SimpleNamespace(
            chat_id=42,
            attributes={"disabled_events": ["NEW_DAY"]},
        )

        with patch(
                "handlers.settings_handlers.edit_rich",
                new_callable=AsyncMock,
        ) as send:
            await edit_alarms(event, driver)

        rich_message = send.await_args.args[1]
        table = next(
            block for block in rich_message.blocks
            if isinstance(block, InputRichBlockTable)
        )
        self.assertEqual(len(table.cells), len(EventType) + 1)
        self.assertEqual(len(table.cells[0]), 4)
        self.assertIsInstance(table.cells[1][2].text, RichTextButton)
        self.assertIsInstance(table.cells[1][3].text, RichTextButton)

        disabled_callback = MyCallback.unpack(
            table.cells[1][2].text.button.callback_data
        )
        enabled_callback = MyCallback.unpack(
            table.cells[2][2].text.button.callback_data
        )
        self.assertEqual(disabled_callback.action, "set-alarms")
        self.assertEqual(disabled_callback.event_type, "NEW_DAY")
        self.assertFalse(disabled_callback.bool_value)
        self.assertTrue(enabled_callback.bool_value)
        self.assertEqual(
            MyCallback.unpack(table.cells[1][3].text.button.callback_data).action,
            "test-alarms",
        )

        self.assertNotIn("reply_markup", send.await_args.kwargs)
        fallback_markup = send.await_args.kwargs["fallback_reply_markup"]
        self.assertEqual(
            sum(len(row) for row in fallback_markup.inline_keyboard),
            len(EventType) * 2 + 1,
        )
        self.assertTrue(
            any(isinstance(block, InputRichBlockButtons) for block in rich_message.blocks)
        )


if __name__ == "__main__":
    unittest.main()
