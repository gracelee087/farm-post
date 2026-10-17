"""Offline outbox: one JSON file per post (+ its image) in OUTBOX_DIR."""
import json
import os
import socket
import uuid
from datetime import datetime
from pathlib import Path

# Module-level so tests can point it at a temp dir.
OUTBOX_DIR = Path(__file__).parent / "outbox"


def _image_ext(image_bytes: bytes) -> str:
    return ".png" if image_bytes.startswith(b"\x89PNG") else ".jpg"


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _records() -> list:
    if not OUTBOX_DIR.exists():
        return []
    files = sorted(OUTBOX_DIR.glob("*.json"))
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


def save(post: dict, image_bytes: bytes) -> str:
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    post_id = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    image_name = post_id + _image_ext(image_bytes)
    (OUTBOX_DIR / image_name).write_bytes(image_bytes)
    _write_json(OUTBOX_DIR / f"{post_id}.json", {
        "id": post_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "pending",
        "post": post,
        "image": image_name,
    })
    return post_id


def pending() -> list:
    return [r for r in _records() if r["status"] == "pending"]


def published() -> list:
    return [r for r in _records() if r["status"] == "published"]


def get(post_id: str) -> dict:
    return json.loads((OUTBOX_DIR / f"{post_id}.json").read_text(encoding="utf-8"))


def update(post_id: str, **fields) -> dict:
    record = {**get(post_id), **fields}
    _write_json(OUTBOX_DIR / f"{post_id}.json", record)
    return record


def mark_published(post_id: str, **fields) -> None:
    """fields: where it was posted (chat, message_id), so stock changes can edit the post later."""
    update(post_id, status="published", **fields)


def is_online(timeout: float = 1.5) -> bool:
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=timeout).close()
        return True
    except OSError:
        return False


def flush(publisher) -> int:
    """Publish all pending posts if online. publisher(records) is called once
    with the pending records; they are marked published only if it succeeds."""
    records = pending()
    if not records or not is_online():
        return 0
    publisher(records)
    for r in records:
        mark_published(r["id"])
    return len(records)
