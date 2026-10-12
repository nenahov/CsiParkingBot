import unittest

from handlers.achievements_handlers import _cell as achievement_cell
from handlers.queue_handlers import _queue_cell
from handlers.reservation_handlers import _cell as reservation_cell
from utils.rich_ui import cell as rich_ui_cell


class RichTableHeaderAlignmentTests(unittest.TestCase):
    def test_achievement_header_is_centered(self):
        self.assertEqual(achievement_cell("Header", header=True).align, "center")

    def test_reservation_header_is_centered(self):
        self.assertEqual(reservation_cell("Header", header=True).align, "center")

    def test_queue_header_is_centered(self):
        self.assertEqual(_queue_cell("Header", header=True).align, "center")

    def test_shared_rich_ui_header_is_centered(self):
        self.assertEqual(rich_ui_cell("Header", header=True).align, "center")

    def test_non_header_alignment_is_preserved(self):
        self.assertEqual(achievement_cell("Body").align, "left")
        self.assertEqual(reservation_cell("Body", align="right").align, "right")
        self.assertEqual(_queue_cell("Body", align="right").align, "right")
        self.assertEqual(rich_ui_cell("Body", align="right").align, "right")


if __name__ == "__main__":
    unittest.main()
