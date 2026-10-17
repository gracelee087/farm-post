"""Telegram bot: the seller sends a photo + short caption from their phone.
This computer writes the listing with local Gemma, sends the draft back with [Post] [Try again],
and on [Post] puts it in the outbox, which publishes to the shop channel (and the local web page).

Only TELEGRAM_BOT_TOKEN is required (env or farm-post/.env). The first person who messages the bot
becomes the owner (saved in owner.txt). Optional TELEGRAM_CHANNEL (e.g. @myshop): posts go there;
without it, the finished post is sent back to the owner to forward anywhere. Run: python bot.py
On a server (Render): python bot.py --webhook, with OWNER_ID set (the bot tells you your ID)."""
import hashlib
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import outbox
import publish_site
import publish_telegram
from generate import generate_post, transcribe

HELP = ("Send me a photo of what you are selling. Then hold 🎙️ and say what it is and the price, "
        "or type it as the photo caption.\nFor example: hand-knitted scarf, wool, $25")
ASK_NOTE = "📷 Got it. Now hold 🎙️ and say what it is and the price (or type it)."
OWNER_FILE = Path(__file__).parent / "owner.txt"
# Our proxy on Render (price-proxy/): it holds the SerpApi key and returns online-shop prices.
PRICE_URL = "https://farm-post-price-proxy.onrender.com"
COUNTRY = {"€": "de", "$": "us", "£": "gb", "₹": "in"}  # currency of the note -> shop country
drafts = {}  # draft id -> {"post", "image", "note"}
waiting = {}  # chat id -> photo sent without a caption, waiting for a voice or text note


def api(method: str, **params) -> dict:
    token = publish_telegram.setting("TELEGRAM_BOT_TOKEN")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}",
                                 data=json.dumps(params).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))["result"]


def download_file(file_id: str) -> bytes:
    token = publish_telegram.setting("TELEGRAM_BOT_TOKEN")
    path = api("getFile", file_id=file_id)["file_path"]
    with urllib.request.urlopen(f"https://api.telegram.org/file/bot{token}/{path}", timeout=60) as resp:
        return resp.read()


def allowed(user_id: int) -> bool:
    """Only the owner may use the bot: OWNER_ID if set (needed on a server, whose files reset),
    else the first user to message it (saved in owner.txt)."""
    owner = publish_telegram.setting("OWNER_ID")
    if owner:
        return owner == str(user_id)
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


def market_price(query: str, price_text: str) -> str:
    """Online-shop prices for similar items as one line for the seller; "" if none found."""
    gl = COUNTRY.get(price_text[:1]) or publish_telegram.setting("SHOP_COUNTRY") or "us"
    url = f"{PRICE_URL}/price?" + urllib.parse.urlencode({"q": query[:100], "gl": gl})
    with urllib.request.urlopen(url, timeout=90) as resp:  # the free server may take ~1 min to wake up
        d = json.loads(resp.read().decode("utf-8"))
    if not d.get("count"):
        return ""
    cur = d.get("currency_hint") or ""
    return (f"💡 Online shops ({gl.upper()}) sell \"{query}\" for {cur}{d['min']:.2f} to {cur}{d['max']:.2f}, "
            f"typical {cur}{d['median']:.2f} ({d['count']} offers). Only a rough guide for a farm or market stall.")


def write_draft(chat_id: int, image: bytes, note: str, draft_id: str = "") -> None:
    api("sendMessage", chat_id=chat_id, text="Writing your listing… (about 30 seconds)")
    draft_id = draft_id or uuid.uuid4().hex[:8]
    post = generate_post(image, note)
    drafts[draft_id] = {"post": post, "image": image, "note": note}
    send_draft(chat_id, draft_id)
    if post.get("search"):
        try:
            line = market_price(post["search"], post["price_text"])
            if line:
                api("sendMessage", chat_id=chat_id, text=line)
        except Exception as e:  # prices are a bonus; the listing is already there
            print("Market price lookup failed:", e)


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
    try:
        if "photo" in msg:
            image = download_file(msg["photo"][-1]["file_id"])  # last = largest size
            if msg.get("caption"):
                write_draft(chat_id, image, msg["caption"])
            else:
                waiting[chat_id] = image
                api("sendMessage", chat_id=chat_id, text=ASK_NOTE)
        elif chat_id in waiting and ("voice" in msg or "text" in msg):
            if "voice" in msg:
                note = transcribe(download_file(msg["voice"]["file_id"]), msg["voice"].get("mime_type", "audio/ogg"))
                api("sendMessage", chat_id=chat_id, text=f"📝 I heard: {note}")
            else:
                note = msg["text"]
            write_draft(chat_id, waiting.pop(chat_id), note)
        else:
            api("sendMessage", chat_id=chat_id, text=f"{HELP}\n\n(Your Telegram ID: {msg['from']['id']})")
    except Exception as e:
        api("sendMessage", chat_id=chat_id, text=f"Sorry, something went wrong: {e}")


def serve(port: int) -> None:
    """Webhook mode for a server (e.g. Render): Telegram calls us, so nothing has to poll."""
    url = os.environ.get("RENDER_EXTERNAL_URL") or publish_telegram.setting("PUBLIC_URL")
    secret = hashlib.sha256(publish_telegram.setting("TELEGRAM_BOT_TOKEN").encode()).hexdigest()[:32]
    api("setWebhook", url=f"{url}/telegram", secret_token=secret)

    def safe_handle(update):
        try:
            handle(update)
        except Exception as e:
            print("Error:", e)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # health check
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def do_POST(self):
            if self.path != "/telegram" or self.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
                self.send_response(403)
                self.end_headers()
                return
            update = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            self.send_response(200)  # answer at once; writing the listing takes a while
            self.end_headers()
            threading.Thread(target=safe_handle, args=(update,)).start()

    print(f"Webhook set to {url}/telegram, listening on port {port}")
    ThreadingHTTPServer(("", port), Handler).serve_forever()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if not publish_telegram.setting("TELEGRAM_BOT_TOKEN"):
        sys.exit("TELEGRAM_BOT_TOKEN is missing (put it in farm-post/.env).")
    if "--webhook" in sys.argv:
        return serve(int(os.environ.get("PORT", "10000")))
    api("deleteWebhook")  # polling and a webhook can't both be active
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
