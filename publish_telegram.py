"""Publisher: posts each listing as a photo + caption to a Telegram channel (Bot API sendPhoto).
Needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL (e.g. @myfarmshop) in the environment or farm-post/.env."""
import json
import os
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


def caption(post: dict) -> str:
    price = " · ".join(p for p in (post.get("price_text"), post.get("unit_price_text")) if p)
    tags = " ".join("#" + t.lstrip("#").replace(" ", "") for t in post.get("tags", []) if t)
    head = "\n".join(p for p in (f"<b>{_esc(post.get('title', ''))}</b>", _esc(price)) if p)
    tail = _esc(tags)
    room = CAPTION_LIMIT - len(head) - len(tail) - 4
    body = post.get("body", "")
    if len(body) > room:
        body = body[:max(room - 1, 0)] + "…"
    return "\n\n".join(p for p in (head, _esc(body), tail) if p)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _send_photo(token, channel, image_path: Path, text: str) -> None:
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in (("chat_id", channel), ("caption", text), ("parse_mode", "HTML")):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
                     .encode("utf-8"))
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="{image_path.name}"\r\n'
                 f"Content-Type: application/octet-stream\r\n\r\n".encode("utf-8"))
    parts.append(image_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8"))
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendPhoto", data=b"".join(parts),
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        reply = json.loads(resp.read().decode("utf-8"))
    if not reply.get("ok"):
        raise RuntimeError(f"Telegram error: {reply.get('description')}")


def publish(records: list, chat: str = "") -> None:
    """Send each record to the channel (or to `chat` if given); mark it published right after
    its own send so a later failure does not cause already-sent listings to be posted twice."""
    token, channel = _config()
    target = chat or channel
    if not (token and target):
        raise RuntimeError("Telegram is not set up (TELEGRAM_BOT_TOKEN / TELEGRAM_CHANNEL missing).")
    for r in records:
        _send_photo(token, target, outbox.OUTBOX_DIR / r["image"], caption(r["post"]))
        outbox.mark_published(r["id"])
