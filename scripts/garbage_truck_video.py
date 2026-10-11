"""Проверочное видео полного маршрута мусоровоза.

Запуск из корня проекта:
    python -m scripts.garbage_truck_video
"""

import asyncio
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from moviepy.video.io.ffmpeg_writer import FFMPEG_VideoWriter

from utils.map_generator import add_garbage_truck, garbage_truck_frames, generate_parking_map


class GarbageTruckVideoPreview:
    """Собирает все кадры маршрута поверх одной неизменной карты парковки."""

    def __init__(self, output_path="pics/temp/garbage_truck_route.mp4", fps=20):
        self.output_path = Path(output_path)
        self.fps = fps

    async def create_mp4(self):
        # Сухая погода и пустая парковка позволяют видеть только движение мусоровоза.
        base = await generate_parking_map(
            [], {}, None, weather_override=("", {"icon": ""}, ""),
            queue_entries=[],
        )
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        # libx264 с yuv420p требует чётной ширины и высоты (map3.png — 941x1672).
        pad_right, pad_bottom = base.width % 2, base.height % 2
        video_size = (base.width + pad_right, base.height + pad_bottom)

        with FFMPEG_VideoWriter(
                str(self.output_path),
                video_size,
                self.fps,
                codec="libx264",
                pixel_format="yuv420p",
                ffmpeg_params=["-movflags", "faststart"],
        ) as writer:
            for frame_index in range(len(garbage_truck_frames)):
                overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
                await add_garbage_truck(frame_index, overlay)
                frame = Image.alpha_composite(base, overlay).convert("RGB")
                if pad_right or pad_bottom:
                    frame = ImageOps.expand(frame, border=(0, 0, pad_right, pad_bottom))
                writer.write_frame(np.asarray(frame))

        return self.output_path


if __name__ == "__main__":
    result = asyncio.run(GarbageTruckVideoPreview().create_mp4())
    print(f"Создано видео: {result.resolve()} ({len(garbage_truck_frames)} кадров)")
