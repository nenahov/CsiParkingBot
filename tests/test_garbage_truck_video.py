import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from PIL import Image

from scripts.garbage_truck_video import GarbageTruckVideoPreview


class GarbageTruckVideoTests(unittest.TestCase):
    def test_writes_every_frame_including_zero_and_last(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "preview.mp4"
            base = Image.new("RGBA", (5, 4), (10, 20, 30, 255))
            visited = []

            async def draw_truck(index, overlay):
                visited.append(index)
                overlay.putpixel((1, 1), (50 + index, 0, 0, 255))

            with (
                patch("scripts.garbage_truck_video.garbage_truck_frames", [0, 1, 2]),
                patch("scripts.garbage_truck_video.generate_parking_map",
                      new_callable=AsyncMock, return_value=base) as make_map,
                patch("scripts.garbage_truck_video.add_garbage_truck",
                      side_effect=draw_truck),
                patch("scripts.garbage_truck_video.FFMPEG_VideoWriter") as writer_class,
            ):
                result = asyncio.run(GarbageTruckVideoPreview(destination, fps=20).create_mp4())

            self.assertEqual(result, destination)
            self.assertEqual(visited, [0, 1, 2])
            self.assertEqual(make_map.await_count, 1)
            self.assertEqual(writer_class.call_args.args[:3], (str(destination), (6, 4), 20))
            frames = [call.args[0] for call in
                      writer_class.return_value.__enter__.return_value.write_frame.call_args_list]
            self.assertEqual(len(frames), 3)
            self.assertEqual([int(frame[1, 1, 0]) for frame in frames], [50, 51, 52])
            self.assertTrue(all(frame.shape == (4, 6, 3) for frame in frames))
