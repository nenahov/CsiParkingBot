import unittest
from types import SimpleNamespace

from aiogram.types import InputRichBlockTable, InputRichMessage

from handlers.shop_handlers import get_shop_rich_content_and_keyboard


class ShopRichUiTests(unittest.IsolatedAsyncioTestCase):
    async def test_shop_table_preserves_stock_and_purchase_callbacks(self):
        driver = SimpleNamespace(
            chat_id=42,
            description="Alex",
            attributes={
                "gender": "M",
                "shop_id": 7,
                "shop_items": [
                    {"price": 10, "description": "Tea", "count": 2, "sold": 1},
                    {"price": 5, "description": "Cookies", "count": 1, "sold": 1},
                    {"price": 3, "description": "Kindness", "count": None, "sold": 0},
                ],
            },
        )

        rich, fallback, legacy_keyboard = await get_shop_rich_content_and_keyboard(
            driver,
            is_private=False,
        )

        self.assertIsInstance(rich, InputRichMessage)
        table = next(block for block in rich.blocks if isinstance(block, InputRichBlockTable))
        self.assertEqual(len(table.cells), 4)
        self.assertEqual(table.cells[1][2].text, "1 / 2")
        self.assertEqual(table.cells[2][2].text, "0 / 1")
        self.assertIn("Tea — 11 💟 — 1 / 2", fallback)
        self.assertIsNotNone(legacy_keyboard.as_markup())


if __name__ == "__main__":
    unittest.main()
