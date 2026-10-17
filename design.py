"""Three ready-to-post designs made from the seller's REAL photo (no AI-generated images):
1 banner, 2 price sticker, 3 clean card. Font: DejaVu Sans in fonts/ (free license, has €₹£)."""
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

FONTS = Path(__file__).parent / "fonts"
SIZE = 1080
WARM = (232, 131, 58)    # autumn orange
DARK = (40, 33, 28)
CREAM = (255, 250, 242)


def _font(size: int, bold: bool = False):
    return ImageFont.truetype(str(FONTS / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")), size)


def _plain(text: str) -> str:
    """The font has no colour emoji, so drop them instead of drawing boxes."""
    return "".join(c for c in text if ord(c) < 0x2000 or c in "€₹₺₩₦₱₫₴₪").strip()


def _wrap(draw, text: str, font, width: int, max_lines: int = 2) -> list:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,") + "…"
    return lines


def _price(post: dict) -> str:
    return " · ".join(p for p in (post.get("price_text"), post.get("unit_price_text")) if p)


def _stock(post: dict) -> str:
    stock = post.get("stock")
    return "SOLD OUT" if stock == 0 else f"Available: {stock}" if isinstance(stock, int) else ""


def _jpeg(img) -> bytes:
    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=88)
    return out.getvalue()


def banner(photo, post: dict) -> bytes:
    img = ImageOps.fit(photo, (SIZE, SIZE))
    band = Image.new("RGBA", (SIZE, 300), (*DARK, 215))
    img.paste(band, (0, SIZE - 300), band)
    draw = ImageDraw.Draw(img)
    y = SIZE - 270
    for line in _wrap(draw, _plain(post["title"]), _font(60, True), SIZE - 120):
        draw.text((60, y), line, font=_font(60, True), fill="white")
        y += 78
    draw.text((60, SIZE - 95), "  ".join(p for p in (_price(post), _stock(post)) if p), font=_font(44), fill=WARM)
    return _jpeg(img)


def sticker(photo, post: dict) -> bytes:
    img = Image.new("RGB", (SIZE, SIZE), WARM)
    img.paste(ImageOps.fit(photo, (SIZE - 80, SIZE - 80)), (40, 40))
    draw = ImageDraw.Draw(img)
    if post.get("price_text"):
        cx, cy, r = SIZE - 210, 210, 150
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=CREAM, outline=DARK, width=6)
        draw.text((cx, cy - 25), post["price_text"], font=_font(62, True), fill=DARK, anchor="mm")
        unit = post.get("unit_price_text") or _stock(post)
        if unit:
            draw.text((cx, cy + 50), unit, font=_font(34), fill=DARK, anchor="mm")
    title = _wrap(draw, _plain(post["title"]), _font(50, True), SIZE - 200, max_lines=1)[0]
    w = draw.textlength(title, font=_font(50, True))
    draw.rounded_rectangle((60, SIZE - 160, 60 + w + 60, SIZE - 70), radius=20, fill=CREAM)
    draw.text((90, SIZE - 115), title, font=_font(50, True), fill=DARK, anchor="lm")
    return _jpeg(img)


def card(photo, post: dict) -> bytes:
    img = Image.new("RGB", (SIZE, SIZE), CREAM)
    img.paste(ImageOps.fit(photo, (SIZE - 120, 640)), (60, 60))
    draw = ImageDraw.Draw(img)
    y = 730
    for line in _wrap(draw, _plain(post["title"]), _font(54, True), SIZE - 120):
        draw.text((60, y), line, font=_font(54, True), fill=DARK)
        y += 68
    draw.text((60, y + 15), _price(post), font=_font(58, True), fill=WARM)
    tags = "  ".join("#" + t.lstrip("#").replace(" ", "") for t in post.get("tags", [])[:3])
    draw.text((60, SIZE - 70), "  ".join(p for p in (_stock(post), tags) if p), font=_font(34), fill=(120, 110, 100))
    return _jpeg(img)


def designs(image_bytes: bytes, post: dict) -> list:
    """The three designs as JPEG bytes, in the order shown to the seller."""
    photo = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    return [banner(photo, post), sticker(photo, post), card(photo, post)]


if __name__ == "__main__":  # python design.py photo.jpg -> design1-3.jpg next to it
    import sys
    from pathlib import Path

    src = Path(sys.argv[1])
    demo = {"title": "Sweet Persimmons from Our Orchard 🧡", "price_text": "€8.00", "unit_price_text": "€1.60/kg",
            "stock": 20, "tags": ["persimmons", "local", "fresh fruit"]}
    for i, jpg in enumerate(designs(src.read_bytes(), demo), 1):
        (src.parent / f"design{i}.jpg").write_bytes(jpg)
