"""Telegram bot: the seller sends a photo + short caption from their phone.
This computer writes the listing with local Gemma, sends the draft back with [Post] [Try again],
and on [Post] puts it in the outbox, which publishes to the shop channel (and the local web page).

Only TELEGRAM_BOT_TOKEN is required (env or farm-post/.env). The first person who messages the bot
becomes the owner (saved in owner.txt). Optional TELEGRAM_CHANNEL (e.g. @myshop): posts go there;
without it, the finished post is sent back to the owner to forward anywhere. Run: python bot.py
On a server (Render): python bot.py --webhook, with OWNER_ID set (the bot tells you your ID)."""
import hashlib
import html
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

import design
import outbox
import publish_site
import publish_telegram
from generate import generate_post, parse_price

HELP = ("Send me a photo of what you are selling. I write the post, then you tap the price.\n"
        "(You can also type a note as the photo caption, e.g. hand-knitted scarf, wool, $25)")
PRICES = ["1", "2", "3", "4", "5", "6", "8", "10", "15", "20"]
UNITS = ["1 kg", "5 kg", "10 kg", "1 piece", "6 pieces", "10 pieces", "1 jar", "1 bag", "1 box"]
STOCKS = ["5", "10", "20", "50", "100"]
ORDER_AMOUNTS = ["1", "2", "3", "5", "10"]
OWNER_FILE = Path(__file__).parent / "owner.txt"
# Our proxy on Render (price-proxy/): it holds the SerpApi key and returns online-shop prices.
PRICE_URL = "https://farm-post-price-proxy.onrender.com"
COUNTRY = {"€": "de", "$": "us", "£": "gb", "₹": "in"}  # currency of the note -> shop country
drafts = {}  # draft id -> {"post", "image", "note", "price"}
waiting = {}  # chat id -> draft id whose price the seller chose to type


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
    text = publish_telegram.caption(d["post"]) + f"\n\n<i>Written by {d['post']['model']} in {d['post']['seconds']:.0f} s.</i>"
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


def send_market_price(chat_id: int, post: dict) -> None:
    if post.get("search"):
        try:
            line = market_price(post["search"], post["price_text"])
            if line:
                api("sendMessage", chat_id=chat_id, text=line)
        except Exception as e:  # prices are a bonus; the listing is already there
            print("Market price lookup failed:", e)


def write_draft(chat_id: int, image: bytes, note: str, draft_id: str = "") -> None:
    api("sendMessage", chat_id=chat_id, text="Writing your listing… (about 30 seconds)")
    draft_id = draft_id or uuid.uuid4().hex[:8]
    post = dict(generate_post(image, note), note=note)
    drafts[draft_id] = {"post": post, "image": image, "original": image, "note": note}
    send_draft(chat_id, draft_id)
    send_market_price(chat_id, post)


# ---- photo only: Gemma writes the post, the seller taps the price ----

def currency() -> str:
    return publish_telegram.setting("SHOP_CURRENCY") or "€"


def last_note(item: str) -> str:
    """The price note of the newest earlier post for the same kind of item (a farm sells the same things again)."""
    words = set(item.lower().split())
    for r in reversed(outbox.published() + outbox.pending()):
        if r["post"].get("note") and words & set(r["post"].get("item", "").lower().split()):
            return r["post"]["note"]
    return ""


def buttons(draft_id: str, action: str, labels: list, per_row: int = 5) -> list:
    keys = [{"text": label, "callback_data": f"{action}:{draft_id}:{i}"} for i, label in enumerate(labels)]
    return [keys[i:i + per_row] for i in range(0, len(keys), per_row)]


def wake_price_server() -> None:
    """The free price server sleeps when idle; wake it while Gemma looks at the photo."""
    def ping():
        try:
            urllib.request.urlopen(f"{PRICE_URL}/health", timeout=90).close()
        except OSError:
            pass
    threading.Thread(target=ping, daemon=True).start()


def start_from_photo(chat_id: int, image: bytes) -> None:
    api("sendMessage", chat_id=chat_id, text="Looking at your photo… (about 30 seconds)")
    wake_price_server()
    draft_id = uuid.uuid4().hex[:8]
    post = dict(generate_post(image, ""), note="")
    drafts[draft_id] = {"post": post, "image": image, "original": image, "note": ""}
    rows = buttons(draft_id, "price", [currency() + p for p in PRICES])
    last = last_note(post["item"])
    if last:
        rows.insert(0, [{"text": f"⭐ {last} (like last time)", "callback_data": f"last:{draft_id}:0"}])
    rows.append([{"text": "✏️ Type it", "callback_data": f"type:{draft_id}:0"}])
    hint = ""
    if post.get("search"):  # show online prices while the seller decides, not after
        try:
            hint = market_price(post["search"], currency())
        except Exception as e:
            print("Market price lookup failed:", e)
    api("sendMessage", chat_id=chat_id, parse_mode="HTML", reply_markup={"inline_keyboard": rows},
        text=f"<b>{html.escape(post['title'])}</b>\n\n" + (f"{html.escape(hint)}\n\n" if hint else "") + "How much?")


def finish(chat_id: int, draft_id: str, note: str) -> None:
    """Put the chosen price on the draft (computed in code, like a typed note) and show it."""
    d = drafts[draft_id]
    d["note"] = d["post"]["note"] = note
    d["post"]["price_text"], d["post"]["unit_price_text"] = parse_price(note)
    rows = buttons(draft_id, "stock", STOCKS) + [[{"text": "Skip", "callback_data": f"stock:{draft_id}:skip"}]]
    api("sendMessage", chat_id=chat_id, text="How many do you have?", reply_markup={"inline_keyboard": rows})


# ---- stock: shown on the post, and the seller taps when things sell ----

def sold_buttons(post_id: str) -> dict:
    return {"inline_keyboard": [[{"text": "➖ 1 sold", "callback_data": f"sold:{post_id}:1"},
                                 {"text": "➖ 5 sold", "callback_data": f"sold:{post_id}:5"},
                                 {"text": "❌ Sold out", "callback_data": f"sold:{post_id}:out"}]]}


def sell(chat_id: int, post_id: str, choice: str) -> None:
    """Lower the stock of a posted listing and edit the channel post to match."""
    r = outbox.get(post_id)
    stock = 0 if choice == "out" else max(0, r["post"]["stock"] - int(choice))
    r = outbox.update(post_id, post={**r["post"], "stock": stock})
    if r.get("message_id"):
        publish_telegram.edit(r)
    api("sendMessage", chat_id=chat_id, text=f"{r['post']['title']}: {publish_telegram.stock_text(r['post'])}",
        **({"reply_markup": sold_buttons(post_id)} if stock else {}))


# ---- designs: three looks made from the real photo, the seller picks one ----

def send_designs(chat_id: int, draft_id: str) -> None:
    d = drafts[draft_id]
    d["designs"] = design.designs(d["original"], d["post"])
    token = publish_telegram.setting("TELEGRAM_BOT_TOKEN")
    for i, jpg in enumerate(d["designs"]):
        publish_telegram.send_photo(token, chat_id, jpg, f"Design {i + 1}", {"inline_keyboard": [[
            {"text": f"✅ Use design {i + 1}", "callback_data": f"design:{draft_id}:{i}"}]]})
    api("sendMessage", chat_id=chat_id, text="Pick a design, or keep your own photo:", reply_markup={
        "inline_keyboard": [[{"text": "📷 My photo as it is", "callback_data": f"design:{draft_id}:orig"}]]})


def redo(chat_id: int, draft_id: str) -> None:
    """Write the text again; keep the seller's price, stock and photo."""
    d = drafts[draft_id]
    api("sendMessage", chat_id=chat_id, text="Writing it again… (about 30 seconds)")
    d["post"] = dict(generate_post(d["original"], d["note"]), note=d["note"], stock=d["post"].get("stock"))
    if "designs" in d:
        send_designs(chat_id, draft_id)
    else:
        send_draft(chat_id, draft_id)


# ---- buying: 🛒 Reserve under a channel post opens this bot for the customer ----

def owner_chat() -> str:
    return publish_telegram.setting("OWNER_ID") or (OWNER_FILE.read_text(encoding="utf-8").strip()
                                                    if OWNER_FILE.exists() else "")


def start_order(chat_id: int, post_id: str) -> None:
    try:
        r = outbox.get(post_id)
    except (OSError, ValueError):
        api("sendMessage", chat_id=chat_id, text="Sorry, this item is no longer listed.")
        return
    stock = r["post"].get("stock")
    if stock == 0:
        api("sendMessage", chat_id=chat_id, text=f"Sorry, {r['post']['title']} is sold out.")
        return
    amounts = [n for n in ORDER_AMOUNTS if stock is None or int(n) <= stock]
    price = " · ".join(p for p in (r["post"].get("price_text"), r["post"].get("unit_price_text")) if p)
    api("sendMessage", chat_id=chat_id, parse_mode="HTML",
        text=f"<b>{html.escape(r['post']['title'])}</b>\n{html.escape(price)}\n"
             f"{publish_telegram.stock_text(r['post'])}\n\nHow many would you like to reserve?",
        reply_markup={"inline_keyboard": [[{"text": n, "callback_data": f"order:{post_id}:{n}"} for n in amounts]]})


def reserve(chat_id: int, user: dict, post_id: str, amount: int) -> None:
    """Take a reservation: lower the stock, update the channel post, tell the customer and the seller."""
    r = outbox.get(post_id)
    stock = r["post"].get("stock")
    if isinstance(stock, int) and amount > stock:
        api("sendMessage", chat_id=chat_id, text=f"Sorry, only {stock} left.")
        return
    order = {"user_id": user["id"], "name": user.get("first_name", ""), "username": user.get("username", ""),
             "amount": amount, "at": time.strftime("%Y-%m-%d %H:%M")}
    post = {**r["post"], "stock": stock - amount if isinstance(stock, int) else stock}
    r = outbox.update(post_id, post=post, orders=r.get("orders", []) + [order])
    if r.get("message_id"):
        publish_telegram.edit(r)
    api("sendMessage", chat_id=chat_id, text=f"✅ Reserved: {amount} × {post['title']} ({post.get('price_text', '')}).\n"
                                             "The farmer will message you about pickup. You pay when you pick it up.")
    if owner_chat():
        who = html.escape(order["name"] or "A customer") + (f" (@{order['username']})" if order["username"] else "")
        api("sendMessage", chat_id=owner_chat(), parse_mode="HTML",
            text=f"🛒 New reservation: <b>{amount} × {html.escape(post['title'])}</b>\n"
                 f"From: <a href=\"tg://user?id={user['id']}\">{who}</a>\n{publish_telegram.stock_text(post)}")


def handle(update: dict) -> None:
    if "callback_query" in update:
        q = update["callback_query"]
        chat_id = q["message"]["chat"]["id"]
        action, _, rest = q["data"].partition(":")
        draft_id, _, choice = rest.partition(":")
        if action == "order":  # customers: anyone may reserve
            api("answerCallbackQuery", callback_query_id=q["id"])
            try:
                reserve(chat_id, q["from"], draft_id, int(choice))
            except Exception as e:
                api("sendMessage", chat_id=chat_id, text=f"Sorry, the reservation did not go through: {e}")
            return
        if not allowed(q["from"]["id"]):
            return
        api("answerCallbackQuery", callback_query_id=q["id"])
        if action == "sold":  # here draft_id is the outbox post id
            try:
                sell(chat_id, draft_id, choice)
            except Exception as e:
                api("sendMessage", chat_id=chat_id, text=f"Could not update the stock: {e}")
            return
        d = drafts.get(draft_id)
        if not d:
            api("sendMessage", chat_id=chat_id, text="That draft is gone. Please send the photo again.")
        elif action == "price":
            d["price"] = PRICES[int(choice)]
            api("sendMessage", chat_id=chat_id, text=f"{currency()}{d['price']} for how much?",
                reply_markup={"inline_keyboard": buttons(draft_id, "unit", UNITS, per_row=3)})
        elif action == "unit":
            finish(chat_id, draft_id, f"{UNITS[int(choice)]} {currency()}{d['price']}")
        elif action == "last":
            finish(chat_id, draft_id, last_note(d["post"]["item"]))
        elif action == "type":
            waiting[chat_id] = draft_id
            api("sendMessage", chat_id=chat_id, text=f"Type the price and amount, e.g. 5 kg {currency()}8")
        elif action == "stock":
            d["post"]["stock"] = None if choice == "skip" else int(STOCKS[int(choice)])
            send_designs(chat_id, draft_id)
        elif action == "design":
            d["image"] = d["original"] if choice == "orig" else d["designs"][int(choice)]
            send_draft(chat_id, draft_id)
        elif action == "redo":
            redo(chat_id, draft_id)
        elif action == "post":
            drafts.pop(draft_id)
            post_id = outbox.save(d["post"], d["image"])
            try:
                sent = outbox.flush(lambda records: publish_all(records, chat_id))
                text = (("Posted to your shop channel. ✅" if publish_telegram.setting("TELEGRAM_CHANNEL")
                         else "Here is your finished post ⬆️ Forward it to your customers. ✅") if sent
                        else "Saved. It will be posted when there is internet.")
                if d["post"].get("stock"):
                    api("sendMessage", chat_id=chat_id, text=text + "\nTap when something sells:",
                        reply_markup=sold_buttons(post_id))
                else:
                    api("sendMessage", chat_id=chat_id, text=text)
            except Exception as e:  # stays in the outbox and is retried on the next post / restart
                api("sendMessage", chat_id=chat_id, text=f"Saved, but posting failed (will retry): {e}")
        return

    msg = update.get("message")
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    if msg.get("text", "").startswith("/start o"):  # a customer tapped 🛒 Reserve under a post
        start_order(chat_id, msg["text"][len("/start o"):].strip())
        return
    if not allowed(msg["from"]["id"]):
        api("sendMessage", chat_id=chat_id,
            text="Hello! To buy something, tap 🛒 Reserve under a post in the shop channel.")
        return
    try:
        if "photo" in msg:
            image = download_file(msg["photo"][-1]["file_id"])  # last = largest size
            if msg.get("caption"):
                write_draft(chat_id, image, msg["caption"])
            else:
                start_from_photo(chat_id, image)
        elif "text" in msg and waiting.get(chat_id) in drafts:
            finish(chat_id, waiting.pop(chat_id), msg["text"])
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
