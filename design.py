"""Four ready-to-post designs made from the seller's REAL photo (no AI-generated images):
banner, chalkboard, polaroid, magazine. Colours are taken from the photo itself.
Fonts in fonts/: DejaVu Sans, Caveat (handwriting), Playfair Display (serif); free licenses, all have €₹£."""
import colorsys
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

FONTS = Path(__file__).parent / "fonts"
SIZE = 1080
INK = (34, 28, 24)
PAPER = (255, 250, 242)


def _font(size: int, bold: bool = False):
    return ImageFont.truetype(str(FONTS / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")), size)


def _plain(text: str) -> str:
    """The font has no colour emoji, so drop them instead of drawing boxes."""
    return "".join(c for c in text if ord(c) < 0x2000 or c in "€₹₺₩₦₱₫₴₪").strip()


def _accent(photo) -> tuple:
    """The photo's strongest colour, made rich enough for text and badges (orange persimmons -> orange)."""
    small = photo.resize((48, 48)).convert("RGB")
    best, score = (200, 110, 50), -1.0
    for r, g, b in small.get_flattened_data():
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s * v > score:
            best, score = (h, s, v), s * v
    h, s, v = best
    r, g, b = colorsys.hsv_to_rgb(h, max(s, 0.55), min(max(v, 0.55), 0.78))
    return int(r * 255), int(g * 255), int(b * 255)


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


def _stock(post: dict) -> str:
    stock = post.get("stock")
    return "SOLD OUT" if stock == 0 else f"{stock} available" if isinstance(stock, int) else ""


def _pill(draw, xy, text, font, fill, color, pad=(26, 14)):
    """A rounded label; returns its right edge."""
    x, y = xy
    w = draw.textlength(text, font=font)
    h = font.size
    draw.rounded_rectangle((x, y, x + w + 2 * pad[0], y + h + 2 * pad[1]), radius=(h + 2 * pad[1]) // 2, fill=fill)
    draw.text((x + pad[0], y + pad[1] + h // 2), text, font=font, fill=color, anchor="lm")
    return x + w + 2 * pad[0]


def _rounded(img, radius: int):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *img.size), radius=radius, fill=255)
    out = Image.new("RGBA", img.size)
    out.paste(img, (0, 0), mask)
    return out


def _shadow(canvas, box, radius: int, blur: int = 18, offset: int = 10):
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    x0, y0, x1, y1 = box
    ImageDraw.Draw(layer).rounded_rectangle((x0, y0 + offset, x1, y1 + offset), radius=radius, fill=(0, 0, 0, 90))
    canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))


def _jpeg(img, post: dict) -> bytes:
    """Save as JPEG, with the listing's ID and date small in the top-right corner."""
    if post.get("ref"):
        draw = ImageDraw.Draw(img)
        text = f"{post['ref']} · {post.get('date', '')}"
        x0 = SIZE - 24 - draw.textlength(text, font=_font(20)) - 16
        draw.rounded_rectangle((x0, 18, SIZE - 24, 52), radius=12, fill=(0, 0, 0, 110) if img.mode == "RGBA" else (60, 60, 60))
        draw.text((SIZE - 32, 35), text, font=_font(20), fill="white", anchor="rm")
    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=90)
    return out.getvalue()


def banner(photo, post: dict) -> bytes:
    """Full photo, dark fade at the bottom, big title and a price pill in the photo's own colour."""
    accent = _accent(photo)
    img = ImageOps.fit(photo, (SIZE, SIZE)).convert("RGBA")
    fade = Image.new("L", (1, SIZE))
    for y in range(SIZE):
        fade.putpixel((0, y), int(235 * max(0.0, (y - SIZE * 0.45) / (SIZE * 0.55)) ** 1.4))
    dark = Image.new("RGBA", (SIZE, SIZE), (*INK, 0))
    dark.putalpha(fade.resize((SIZE, SIZE)))
    img.alpha_composite(dark)
    draw = ImageDraw.Draw(img)
    _pill(draw, (60, 60), "FRESH FROM THE FARM", _font(28, True), (*PAPER, 230), INK)
    lines = _wrap(draw, _plain(post["title"]), _font(66, True), SIZE - 120)
    y = SIZE - 190 - 80 * len(lines)
    for line in lines:
        draw.text((60, y), line, font=_font(66, True), fill="white")
        y += 80
    x = 60
    if post.get("price_text"):
        x = _pill(draw, (60, SIZE - 160), post["price_text"], _font(48, True), accent, "white") + 20
    small = "  ·  ".join(p for p in (post.get("unit_price_text"), _stock(post)) if p)
    if small:
        draw.text((x, SIZE - 160 + 38), small, font=_font(36), fill=(255, 255, 255, 230), anchor="lm")
    return _jpeg(img, post)


def _hand(size: int, bold: bool = True):
    f = ImageFont.truetype(str(FONTS / "Caveat.ttf"), size)
    f.set_variation_by_name("Bold" if bold else "Regular")
    return f


def _serif(size: int, weight: str = "Bold"):
    f = ImageFont.truetype(str(FONTS / "PlayfairDisplay.ttf"), size)
    f.set_variation_by_name(weight)
    return f


def _unit_line(post: dict) -> str:
    return "  ·  ".join(p for p in (post.get("unit_price_text"), _stock(post)) if p)


def chalkboard(photo, post: dict) -> bytes:
    """Farm-stand chalkboard: wooden frame, photo pinned on top, prices written in chalk."""
    img = Image.new("RGBA", (SIZE, SIZE), (122, 82, 48, 255))
    board = Image.effect_noise((SIZE - 60, SIZE - 60), 18).convert("RGB")
    board = Image.blend(Image.new("RGB", board.size, (38, 52, 42)), board, 0.08)
    img.paste(board, (30, 30))
    box = (110, 90, SIZE - 110, 600)
    _shadow(img, box, 6, blur=12, offset=8)
    framed = ImageOps.expand(ImageOps.fit(photo, (box[2] - box[0] - 24, box[3] - box[1] - 24)), 12, fill=(245, 242, 232))
    img.paste(framed.rotate(-1.5, resample=Image.BICUBIC, expand=False, fillcolor=(38, 52, 42)), box[:2])
    draw = ImageDraw.Draw(img)
    chalk, yellow = (240, 236, 225), (244, 211, 94)
    y = 640
    for line in _wrap(draw, _plain(post["title"]), _hand(84), SIZE - 180):
        draw.text((SIZE // 2, y), line, font=_hand(84), fill=chalk, anchor="ma")
        y += 86
    if post.get("price_text"):
        draw.text((SIZE // 2, y + 10), post["price_text"], font=_hand(130), fill=yellow, anchor="ma")
        y += 150
    if _unit_line(post):
        draw.text((SIZE // 2, min(y + 10, SIZE - 110)), _unit_line(post), font=_hand(54, False), fill=chalk, anchor="ma")
    return _jpeg(img, post)


def polaroid(photo, post: dict) -> bytes:
    """A tilted polaroid on warm paper, with a strip of tape and a handwritten caption."""
    accent = _accent(photo)
    img = Image.new("RGBA", (SIZE, SIZE), (*tuple(int(c * 0.12 + 245 * 0.88) for c in accent), 255))
    snap = Image.new("RGBA", (800, 960), (255, 255, 255, 255))
    snap.paste(ImageOps.fit(photo, (720, 720)), (40, 40))
    d = ImageDraw.Draw(snap)
    title = _wrap(d, _plain(post["title"]), _hand(64), 720, max_lines=1)[0]
    d.text((400, 790), title, font=_hand(64), fill=INK, anchor="ma")
    price = "   ".join(p for p in (post.get("price_text"), post.get("unit_price_text")) if p)
    if price:
        d.text((400, 868), price, font=_hand(60), fill=accent, anchor="ma")
    snap = snap.rotate(4, resample=Image.BICUBIC, expand=True)
    x, y = (SIZE - snap.width) // 2, (SIZE - snap.height) // 2 + 10
    _shadow(img, (x + 40, y + 40, x + snap.width - 40, y + snap.height - 40), 4, blur=20, offset=14)
    img.alpha_composite(snap, (x, y))
    tape = Image.new("RGBA", (240, 70), (*accent, 140)).rotate(-6, expand=True)
    img.alpha_composite(tape, (SIZE // 2 - 120, y - 10))
    if _stock(post):
        ImageDraw.Draw(img).text((SIZE - 60, SIZE - 50), _stock(post), font=_hand(48), fill=INK, anchor="rs")
    return _jpeg(img, post)


def magazine(photo, post: dict) -> bytes:
    """Minimal magazine page: big photo, lots of white space, serif title."""
    accent = _accent(photo)
    img = Image.new("RGBA", (SIZE, SIZE), (*PAPER, 255))
    img.paste(ImageOps.fit(photo, (SIZE, 640)), (0, 0))
    draw = ImageDraw.Draw(img)
    x, y = 80, 690
    for ch in "FROM THE FARM":
        draw.text((x, y), ch, font=_font(22, True), fill=(140, 130, 120))
        x += draw.textlength(ch, font=_font(22, True)) + 5
    y += 48
    for line in _wrap(draw, _plain(post["title"]), _serif(62), SIZE - 160):
        draw.text((80, y), line, font=_serif(62), fill=INK)
        y += 76
    draw.line((80, y + 20, 200, y + 20), fill=accent, width=4)
    if post.get("price_text"):
        draw.text((80, y + 45), post["price_text"], font=_serif(54, "Regular"), fill=accent)
        px = 80 + draw.textlength(post["price_text"], font=_serif(54, "Regular")) + 22
        if _unit_line(post):
            draw.text((px, y + 68), _unit_line(post), font=_font(28), fill=(120, 110, 100))
    return _jpeg(img, post)


def designs(image_bytes: bytes, post: dict) -> list:
    """The designs as JPEG bytes, in the order shown to the seller."""
    photo = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    return [banner(photo, post), chalkboard(photo, post), polaroid(photo, post), magazine(photo, post)]


if __name__ == "__main__":  # python design.py photo.jpg -> design1-3.jpg next to it
    import sys

    src = Path(sys.argv[1])
    demo = {"title": "Sweet Persimmons from Our Orchard 🧡", "price_text": "€8.00", "unit_price_text": "€1.60/kg",
            "stock": 20, "tags": ["persimmons", "local", "fresh fruit"], "ref": "1017-6EC1", "date": "17 Oct 2026"}
    for i, jpg in enumerate(designs(src.read_bytes(), demo), 1):
        (src.parent / f"{src.stem}-design{i}.jpg").write_bytes(jpg)
