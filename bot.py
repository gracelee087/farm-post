"""Telegram bot: the seller sends a photo + short caption from their phone.
This computer writes the listing with local Gemma, sends the draft back with [Post] [Try again],
and on [Post] puts it in the outbox, which publishes to the shop channel (and the local web page).

Only TELEGRAM_BOT_TOKEN is required (env or farm-post/.env). The first person who messages the bot
becomes the owner (saved in owner.txt). Optional TELEGRAM_CHANNEL (e.g. @myshop): posts go there;
without it, the finished post is sent back to the owner to forward anywhere. Run: python bot.py"""
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import outbox
import publish_site
import publish_telegram
from generate import generate_post

HELP = ("Send me a photo of what you are selling, with a short note as the caption.\n"
        "For example: hand-knitted scarf, wool, $25")
OWNER_FILE = Path(__file__).parent / "owner.txt"
drafts = {}  # draft id -> {"post", "image", "note"}


def api(method: str, **params) -> dict:
    token = publish_telegram.setting("TELEGRAM_BOT_TOKEN")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}",
                                 data=json.dumps(params).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))["result"]


def download_photo(file_id: str) -> bytes:
    token = publish_telegram.setting("TELEGRAM_BOT_TOKEN")
    path = api("getFile", file_id=file_id)["file_path"]
    with urllib.request.urlopen(f"https://api.telegram.org/file/bot{token}/{path}", timeout=60) as resp:
        return resp.read()


def allowed(user_id: int) -> bool:
    """The first user to message the bot becomes the owner; only the owner may use it."""
    if not OWNER_FILE.exists():
        OWNER_FILE.write_text(str(user_id), encoding="utf-8")
    return OWNER_FILE.read_text(encoding="utf-8").strip() == str(user_id)


def publish_all(records, chat=""):
    publish_site.publish(records)
    if publish_telegram.setting("TELEGRAM_CHANNEL"):
        publish_telegram.publish(records)
    else:
        publish_telegram.publish(records, chat=str(chat))


def send_draft(chat_id: int, draft_id: str) -> None:
    d = drafts[draft_id]
    text = publish_telegram.caption(d["post"]) + f"\n\n<i>Written in {d['post']['seconds']:.0f} s on this computer.</i>"
    api("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML", reply_markup={"inline_keyboard": [[
        {"text": "✅ Post", "callback_data": f"post:{draft_id}"},
        {"text": "🔄 Try again", "callback_data": f"redo:{draft_id}"},
    ]]})


def write_draft(chat_id: int, image: bytes, note: str, draft_id: str = "") -> None:
    api("sendMessage", chat_id=chat_id, text="Writing your listing… (about 30 seconds)")
    draft_id = draft_id or uuid.uuid4().hex[:8]
    drafts[draft_id] = {"post": generate_post(image, note), "image": image, "note": note}
    send_draft(chat_id, draft_id)


def handle(update: dict) -> None:
    if "callback_query" in update:
        q = update["callback_query"]
        chat_id = q["message"]["chat"]["id"]
        if not allowed(q["from"]["id"]):
            return
        action, _, draft_id = q["data"].partition(":")
        api("answerCallbackQuery", callback_query_id=q["id"])
        d = drafts.get(draft_id)
        if not d:
            api("sendMessage", chat_id=chat_id, text="That draft is gone. Please send the photo again.")
        elif action == "redo":
            write_draft(chat_id, d["image"], d["note"], draft_id)
        elif action == "post":
            drafts.pop(draft_id)
            outbox.save(d["post"], d["image"])
            try:
                sent = outbox.flush(lambda records: publish_all(records, chat_id))
                api("sendMessage", chat_id=chat_id,
                    text=("Posted to your shop channel. ✅" if publish_telegram.setting("TELEGRAM_CHANNEL")
                          else "Here is your finished post ⬆️ Forward it to your customers. ✅") if sent else "Saved. It will be posted when there is internet.")
            except Exception as e:  # stays in the outbox and is retried on the next post / restart
                api("sendMessage", chat_id=chat_id, text=f"Saved, but posting failed (will retry): {e}")
        return

    msg = update.get("message")
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    if not allowed(msg["from"]["id"]):
        api("sendMessage", chat_id=chat_id,
            text="Sorry, this shop bot is private.")
        return
    if "photo" not in msg:
        api("sendMessage", chat_id=chat_id, text=HELP)
        return
    try:
        image = download_photo(msg["photo"][-1]["file_id"])  # last = largest size
        write_draft(chat_id, image, msg.get("caption", ""))
    except Exception as e:
        api("sendMessage", chat_id=chat_id, text=f"Sorry, something went wrong: {e}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if not publish_telegram.setting("TELEGRAM_BOT_TOKEN"):
        sys.exit("TELEGRAM_BOT_TOKEN is missing (put it in farm-post/.env).")
    print("Bot running. Send it a photo from your phone. Ctrl+C to stop.")
    offset = 0
    while True:
        try:
            for update in api("getUpdates", offset=offset, timeout=50):
                offset = update["update_id"] + 1
                handle(update)
            if outbox.pending() and OWNER_FILE.exists():  # back online: post what was saved offline
                outbox.flush(lambda records: publish_all(records, OWNER_FILE.read_text(encoding="utf-8").strip()))
        except (urllib.error.URLError, TimeoutError, OSError) as e:  # offline: wait and retry
            print("No connection, retrying in 10 s:", e)
            time.sleep(10)
        except Exception as e:  # e.g. a Telegram error while posting; keep the bot alive
            print("Error:", e)
            time.sleep(10)


if __name__ == "__main__":
    main()
