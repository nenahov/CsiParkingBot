import importlib
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.types import InputRichBlockButtons, InputRichBlockTable, RichTextButton

from handlers.driver_callback import MyCallback
from services.notification_sender import EventType

_settings_module = None


def load_settings_module():
    """Load settings UI without importing its unrelated image-carousel stack."""
    global _settings_module
    if _settings_module is not None:
        return _settings_module
    carousel_stub = types.ModuleType("utils.cars_generator")
    carousel_stub.generate_carousel_image = lambda *args, **kwargs: None
    carousel_stub.generate_avatar_gallery_image = lambda *args, **kwargs: None
    carousel_stub.generate_avatar_preview_image = lambda *args, **kwargs: None
    carousel_stub.cars_count = 0
    carousel_stub.extra_cars_count = 0
    with patch.dict(sys.modules, {"utils.cars_generator": carousel_stub}):
        _settings_module = importlib.import_module("handlers.settings_handlers")
    return _settings_module


class SettingsRichUiTests(unittest.IsolatedAsyncioTestCase):
    async def test_notification_settings_use_rich_actions_with_legacy_fallback(self):
        settings_module = load_settings_module()
        edit_alarms = settings_module.edit_alarms
        event = SimpleNamespace(
            message=SimpleNamespace(chat=SimpleNamespace(type="private"))
        )
        driver = SimpleNamespace(
            chat_id=42,
            attributes={"disabled_events": ["NEW_DAY"]},
        )

        with patch.object(
                settings_module,
                "edit_rich",
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

    def test_avatar_gallery_has_twelve_numbered_rich_actions_per_full_page(self):
        settings_module = load_settings_module()
        with patch.object(
                settings_module,
                "generate_avatar_gallery_image",
                return_value=__import__("io").BytesIO(b"image"),
        ):
            rich = settings_module.build_avatar_gallery_rich_message(
                page=1,
                cars_count_for_driver=60,
                chat_id=42,
                current_index=17,
            )

        table = next(
            block for block in rich.blocks
            if isinstance(block, InputRichBlockTable)
        )
        self.assertEqual(len(table.cells), 4)
        self.assertTrue(all(len(row) == 3 for row in table.cells))
        callbacks = [
            MyCallback.unpack(cell.text.button.callback_data)
            for row in table.cells
            for cell in row
        ]
        self.assertEqual([callback.spot_id for callback in callbacks],
                         list(range(12, 24)))
        self.assertTrue(
            any(isinstance(block, InputRichBlockButtons) for block in rich.blocks)
        )

    def test_avatar_preview_rich_actions_preserve_selected_index(self):
        settings_module = load_settings_module()
        with patch.object(
                settings_module,
                "generate_avatar_preview_image",
                return_value=__import__("io").BytesIO(b"image"),
        ):
            rich = settings_module.build_avatar_preview_rich_message(
                page=2,
                cars_count_for_driver=60,
                chat_id=42,
                avatar_index=29,
            )

        controls = next(
            block for block in rich.blocks
            if isinstance(block, InputRichBlockButtons)
        )
        callbacks = [MyCallback.unpack(button.callback_data) for button in controls.buttons]
        self.assertEqual(callbacks[0].action, "set-avatar")
        self.assertEqual(callbacks[0].spot_id, 29)
        self.assertEqual(callbacks[1].action, "avatar-page")
        self.assertEqual(callbacks[1].spot_id, 2)
        self.assertEqual(len(callbacks), 2)

    def test_avatar_page_count_and_fallback_keyboard_boundaries(self):
        settings_module = load_settings_module()
        self.assertEqual(settings_module.get_avatar_page_count(60), 5)
        self.assertEqual(settings_module.get_avatar_page_count(13), 2)
        self.assertEqual(settings_module.get_avatar_page_count(0), 1)

        keyboard = settings_module.get_avatar_gallery_keyboard(4, 50, 42, 49)
        callbacks = [
            MyCallback.unpack(button.callback_data)
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data.startswith("dcb:")
        ]
        avatar_callbacks = [callback for callback in callbacks
                            if callback.action == "avatar-preview"]
        self.assertEqual([callback.spot_id for callback in avatar_callbacks],
                         [48, 49])
        page_callbacks = [callback for callback in callbacks
                          if callback.action == "avatar-page"]
        self.assertEqual(page_callbacks[0].spot_id, 3)
        self.assertEqual(page_callbacks[-1].spot_id, 4)

    def test_avatar_preview_fallback_has_only_confirm_and_back(self):
        settings_module = load_settings_module()
        keyboard = settings_module.get_avatar_preview_keyboard(2, 60, 42, 29)
        buttons = [
            button
            for row in keyboard.inline_keyboard
            for button in row
        ]
        callbacks = [MyCallback.unpack(button.callback_data) for button in buttons]
        self.assertEqual([callback.action for callback in callbacks],
                         ["set-avatar", "avatar-page"])


if __name__ == "__main__":
    unittest.main()
