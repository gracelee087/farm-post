"""Publisher: posts each listing as a photo + caption to a Telegram channel (Bot API sendPhoto).
Needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL (e.g. @myfarmshop) in the environment or farm-post/.env."""
import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import outbox

ENV_FILE = Path(__file__).parent / ".env"
CAPTION_LIMIT = 1024  # Telegram caption limit (characters)


def setting(name: str) -> str:
    """Value from the environment, else from farm-post/.env, else ""."""
    if os.environ.get(name):
        return os.environ[name]
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name:
                return value.strip().strip('"')
    return ""


def _config():
    return setting("TELEGRAM_BOT_TOKEN"), setting("TELEGRAM_CHANNEL")


def configured() -> bool:
    return all(_config())


def stock_text(post: dict) -> str:
    stock = post.get("stock")
    if stock == 0:
        return "❌ SOLD OUT"
    return f"Available: {stock}" if isinstance(stock, int) else ""


def caption(post: dict) -> str:
    price = " · ".join(p for p in (post.get("price_text"), post.get("unit_price_text")) if p)
    tags = " ".join("#" + t.lstrip("#").replace(" ", "") for t in post.get("tags", []) if t)
    head = "\n".join(p for p in (f"<b>{_esc(post.get('title', ''))}</b>", _esc(price), stock_text(post)) if p)
    stamp = f"Ref {post['ref']} · {post.get('date', '')}" if post.get("ref") else ""
    tail = "\n".join(p for p in (_esc(tags), f"<i>{_esc(stamp)}</i>" if stamp else "") if p)
    room = CAPTION_LIMIT - len(head) - len(tail) - 4
    body = post.get("body", "")
    if len(body) > room:
        body = body[:max(room - 1, 0)] + "…"
    return "\n\n".join(p for p in (head, _esc(body), tail) if p)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _check(reply: dict) -> dict:
    if not reply.get("ok"):
        raise RuntimeError(f"Telegram error: {reply.get('description')}")
    return reply.get("result", {})


def send_photo(token, chat, image: bytes, text: str, reply_markup=None) -> dict:
    boundary = uuid.uuid4().hex
    fields = [("chat_id", chat), ("caption", text), ("parse_mode", "HTML")]
    if reply_markup:
        fields.append(("reply_markup", json.dumps(reply_markup)))
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8")
             for name, value in fields]
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="photo.jpg"\r\n'
                 f"Content-Type: application/octet-stream\r\n\r\n".encode("utf-8"))
    parts.append(image + f"\r\n--{boundary}--\r\n".encode("utf-8"))
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendPhoto", data=b"".join(parts),
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return _check(json.loads(resp.read().decode("utf-8")))


_bot_name = []


def bot_username() -> str:
    """The bot's @username (BOT_USERNAME setting, else asked once with getMe)."""
    if not _bot_name:
        name = setting("BOT_USERNAME")
        if not name:
            with urllib.request.urlopen(f"https://api.telegram.org/bot{setting('TELEGRAM_BOT_TOKEN')}/getMe",
                                        timeout=30) as resp:
                name = _check(json.loads(resp.read().decode("utf-8"))).get("username", "")
        _bot_name.append(name)
    return _bot_name[0]


def order_button(record: dict):
    """🛒 Reserve opens a chat with the bot (t.me deep link), which takes the order; none when sold out."""
    if record["post"].get("stock") == 0 or not bot_username():
        return None
    return {"inline_keyboard": [[{"text": "🛒 Reserve", "url": f"https://t.me/{bot_username()}?start=o{record['id']}"}]]}


def publish(records: list, chat: str = "") -> None:
    """Send each record to the channel (or to `chat` if given); mark it published right after
    its own send so a later failure does not cause already-sent listings to be posted twice."""
    token, channel = _config()
    target = chat or channel
    if not (token and target):
        raise RuntimeError("Telegram is not set up (TELEGRAM_BOT_TOKEN / TELEGRAM_CHANNEL missing).")
    for r in records:
        sent = send_photo(token, target, (outbox.OUTBOX_DIR / r["image"]).read_bytes(), caption(r["post"]),
                          order_button(r))
        outbox.mark_published(r["id"], chat=target, message_id=sent.get("message_id"))


def edit(record: dict) -> None:
    """Rewrite an already posted listing (e.g. new stock) with editMessageCaption."""
    params = {"chat_id": record["chat"], "message_id": record["message_id"],
              "caption": caption(record["post"]), "parse_mode": "HTML"}
    markup = order_button(record)
    if markup:  # without it Telegram drops the button, which is what we want when sold out
        params["reply_markup"] = markup
    req = urllib.request.Request(f"https://api.telegram.org/bot{setting('TELEGRAM_BOT_TOKEN')}/editMessageCaption",
                                 data=json.dumps(params).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            _check(json.loads(resp.read().decode("utf-8")))
    except urllib.error.HTTPError as e:  # Telegram answers errors with HTTP 400 + JSON
        _check(json.loads(e.read().decode("utf-8")))
