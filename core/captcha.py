import io
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LENGTH = 6
WIDTH, HEIGHT = 360, 120

_rng = random.SystemRandom()


def make_code(length: int = LENGTH) -> str:
    return "".join(_rng.choice(ALPHABET) for _ in range(length))


def _color(low: int, high: int) -> tuple[int, int, int]:
    return _rng.randint(low, high), _rng.randint(low, high), _rng.randint(low, high)


def render(code: str) -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), _color(225, 250))
    draw = ImageDraw.Draw(image)

    for _ in range(60):
        x, y = _rng.randint(0, WIDTH), _rng.randint(0, HEIGHT)
        draw.ellipse((x, y, x + 3, y + 3), fill=_color(150, 215))
    for _ in range(5):
        draw.line(
            [(_rng.randint(0, WIDTH), _rng.randint(0, HEIGHT)), (_rng.randint(0, WIDTH), _rng.randint(0, HEIGHT))],
            fill=_color(140, 210),
            width=_rng.randint(1, 3),
        )

    font = ImageFont.load_default(size=54)
    step = (WIDTH - 40) // len(code)
    x = 20
    for char in code:
        tile = Image.new("RGBA", (70, 100), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((10, 12), char, font=font, fill=_color(20, 120) + (255,))
        tile = tile.rotate(_rng.uniform(-20, 20), resample=Image.Resampling.BICUBIC, expand=True)
        image.paste(tile, (x - 4, _rng.randint(0, 18)), tile)
        x += step

    for _ in range(3):
        draw.line(
            [(0, _rng.randint(20, HEIGHT - 20)), (WIDTH, _rng.randint(20, HEIGHT - 20))],
            fill=_color(110, 170),
            width=1,
        )
    image = image.filter(ImageFilter.SMOOTH)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
