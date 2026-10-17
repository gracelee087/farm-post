import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bot  # noqa: E402
import outbox  # noqa: E402
import publish_site  # noqa: E402
import publish_telegram  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0fake-jpeg"
POST = {"item": "Wool scarf", "title": "Warm Hand-Knitted Scarf", "body": "Soft wool.", "price_text": "$25.00",
        "unit_price_text": "", "tags": ["scarf"], "model": "gemma4:e4b", "seconds": 30.0}
SELLER = 42


def photo_update(user=SELLER):
    return {"update_id": 1, "message": {"chat": {"id": 7}, "from": {"id": user},
                                        "photo": [{"file_id": "small"}, {"file_id": "big"}],
                                        "caption": "scarf, wool, $25"}}


def button(data):
    return {"update_id": 2, "callback_query": {"id": "q", "data": data, "from": {"id": SELLER},
                                               "message": {"chat": {"id": 7}}}}


class BotTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = {"TELEGRAM_BOT_TOKEN": "T", "TELEGRAM_CHANNEL": ""}
        owner = Path(tmp.name) / "owner.txt"
        owner.write_text(str(SELLER), encoding="utf-8")
        for p in (mock.patch.object(outbox, "OUTBOX_DIR", Path(tmp.name) / "outbox"),
                  mock.patch.object(bot, "OWNER_FILE", owner),
                  mock.patch.object(publish_site, "SITE_DIR", Path(tmp.name) / "site"),
                  mock.patch.object(publish_telegram, "setting", lambda name: env.get(name, "")),  # ignore a real .env
                  mock.patch.object(outbox, "is_online", return_value=True),
                  mock.patch.object(bot, "download_file", return_value=JPEG),
                  mock.patch.object(bot, "generate_post", return_value=dict(POST))):
            p.start()
            self.addCleanup(p.stop)
        self.api = mock.patch.object(bot, "api").start()
        self.tg_publish = mock.patch.object(publish_telegram, "publish").start()
        self.tg_photo = mock.patch.object(publish_telegram, "send_photo").start()
        self.tg_edit = mock.patch.object(publish_telegram, "edit").start()
        mock.patch.object(bot.design, "designs", return_value=[b"d1", b"d2", b"d3"]).start()
        mock.patch.object(bot, "wake_price_server").start()
        self.addCleanup(mock.patch.stopall)
        bot.drafts.clear()
        bot.waiting.clear()

    def sent_texts(self):
        return [c.kwargs.get("text", "") for c in self.api.call_args_list if c.args[0] == "sendMessage"]

    def test_photo_gives_draft_with_buttons(self):
        bot.handle(photo_update())
        bot.download_file.assert_called_once_with("big")
        bot.generate_post.assert_called_once_with(JPEG, "scarf, wool, $25")
        draft = self.api.call_args_list[-1].kwargs
        self.assertIn("Warm Hand-Knitted Scarf", draft["text"])
        buttons = [b["callback_data"] for b in draft["reply_markup"]["inline_keyboard"][0]]
        self.assertEqual([b.split(":")[0] for b in buttons], ["post", "redo"])

    def test_post_button_saves_and_publishes(self):
        bot.handle(photo_update())
        [draft_id] = bot.drafts
        bot.handle(button(f"post:{draft_id}"))
        self.assertEqual(len(outbox.published()), 1)
        self.assertTrue((publish_site.SITE_DIR / "index.html").exists())
        self.tg_publish.assert_called_once()
        self.assertEqual(self.tg_publish.call_args.kwargs, {"chat": "7"})  # no channel -> back to seller
        self.assertIn("Forward it", self.sent_texts()[-1])
        self.assertEqual(bot.drafts, {})

    def test_redo_regenerates_same_draft(self):
        bot.handle(photo_update())
        [draft_id] = bot.drafts
        bot.handle(button(f"redo:{draft_id}"))
        self.assertEqual(bot.generate_post.call_count, 2)
        self.assertEqual(list(bot.drafts), [draft_id])

    def test_stranger_is_refused_with_their_id(self):
        bot.handle(photo_update(user=555))
        bot.generate_post.assert_not_called()
        self.assertIn("Reserve", self.sent_texts()[-1])

    def test_first_user_becomes_owner(self):
        bot.OWNER_FILE.unlink()
        bot.handle(photo_update(user=123))
        self.assertEqual(bot.OWNER_FILE.read_text(), "123")
        bot.generate_post.assert_called_once()

    def test_market_price_sent_after_draft(self):
        bot.generate_post.return_value = dict(POST, search="wool scarf")
        with mock.patch.object(bot, "market_price", return_value="💡 Online shops (US) ...") as mp:
            bot.handle(photo_update())
        mp.assert_called_once_with("wool scarf", "$25.00")
        self.assertEqual(self.sent_texts()[-1], "💡 Online shops (US) ...")

    def test_market_price_failure_keeps_draft(self):
        bot.generate_post.return_value = dict(POST, search="wool scarf")
        with mock.patch.object(bot, "market_price", side_effect=OSError("down")):
            bot.handle(photo_update())
        self.assertEqual(len(bot.drafts), 1)
        self.assertIn("Warm Hand-Knitted Scarf", self.sent_texts()[-1])

    def test_market_price_line_from_proxy_json(self):
        reply = mock.MagicMock()
        reply.__enter__.return_value.read.return_value = (
            b'{"query":"wool scarf","gl":"de","count":3,"min":10,"median":20,"max":40,"currency_hint":"\\u20ac"}')
        with mock.patch("urllib.request.urlopen", return_value=reply) as urlopen:
            line = bot.market_price("wool scarf", "€25.00")
        self.assertIn("gl=de", urlopen.call_args.args[0])
        self.assertIn("€10.00 to €40.00, typical €20.00 (3 offers)", line)

    def test_text_only_gets_help(self):
        bot.handle({"update_id": 3, "message": {"chat": {"id": 7}, "from": {"id": SELLER}, "text": "hi"}})
        self.assertEqual(self.sent_texts()[-1], f"{bot.HELP}\n\n(Your Telegram ID: {SELLER})")

    def photo_only(self):
        update = photo_update()
        del update["message"]["caption"]
        bot.handle(update)
        [draft_id] = bot.drafts
        return draft_id

    def last_keyboard(self):
        return self.api.call_args_list[-1].kwargs["reply_markup"]["inline_keyboard"]

    def test_photo_only_then_tap_price_and_unit(self):
        draft_id = self.photo_only()
        bot.generate_post.assert_called_once_with(JPEG, "")
        labels = [b["text"] for row in self.last_keyboard() for b in row]
        self.assertEqual(labels[:3], ["€1", "€2", "€3"])
        self.assertEqual(labels[-1], "✏️ Type it")
        bot.handle(button(f"price:{draft_id}:{bot.PRICES.index('8')}"))
        self.assertIn("1 kg", [b["text"] for row in self.last_keyboard() for b in row])
        bot.handle(button(f"unit:{draft_id}:{bot.UNITS.index('5 kg')}"))
        post = bot.drafts[draft_id]["post"]
        self.assertEqual((post["note"], post["price_text"], post["unit_price_text"]), ("5 kg €8", "€8.00", "€1.60/kg"))
        bot.generate_post.assert_called_once()  # tapping the price doesn't call the model again

    def test_market_price_shown_with_the_price_question(self):
        bot.generate_post.return_value = dict(POST, search="persimmons")
        with mock.patch.object(bot, "market_price", return_value="💡 Online shops (DE) ...") as mp:
            self.photo_only()
        mp.assert_called_once_with("persimmons", "€")
        question = self.sent_texts()[-1]
        self.assertIn("💡 Online shops (DE) ...", question)
        self.assertTrue(question.endswith("How much?"))

    def test_every_listing_gets_id_and_date(self):
        draft_id = self.photo_only()
        post = bot.drafts[draft_id]["post"]
        self.assertRegex(post["ref"], r"^\d{4}-[0-9A-F]{4}$")
        self.assertIn(f"[{post['ref']}]", self.sent_texts()[-1])  # shown with the price question
        self.assertIn(f"Ref {post['ref']} · {post['date']}", publish_telegram.caption(post))  # and on the post

    def test_photo_only_then_type_price(self):
        draft_id = self.photo_only()
        bot.handle(button(f"type:{draft_id}:0"))
        bot.handle({"update_id": 5, "message": {"chat": {"id": 7}, "from": {"id": SELLER}, "text": "6 jars $4"}})
        self.assertEqual(bot.drafts[draft_id]["post"]["price_text"], "$4.00")
        self.assertEqual(bot.waiting, {})

    def test_same_price_as_last_time(self):
        outbox.save(dict(POST, item="Fresh persimmons", note="5 kg €8"), JPEG)
        bot.generate_post.return_value = dict(POST, item="persimmons")
        draft_id = self.photo_only()
        first = self.last_keyboard()[0][0]
        self.assertEqual(first["text"], "⭐ 5 kg €8 (like last time)")
        bot.handle(button(first["callback_data"]))
        self.assertEqual(bot.drafts[draft_id]["post"]["unit_price_text"], "€1.60/kg")

    def test_stock_then_post_then_sold(self):
        draft_id = self.photo_only()
        bot.handle(button(f"price:{draft_id}:{bot.PRICES.index('3')}"))
        bot.handle(button(f"unit:{draft_id}:{bot.UNITS.index('1 jar')}"))
        self.assertEqual(self.sent_texts()[-1], "How many do you have?")
        bot.handle(button(f"stock:{draft_id}:{bot.STOCKS.index('20')}"))
        self.assertEqual(self.tg_photo.call_count, 3)  # three designs to pick from
        bot.handle(button(f"design:{draft_id}:1"))
        self.assertIn("Available: 20", self.sent_texts()[-1])
        bot.handle(button(f"post:{draft_id}"))
        [record] = outbox.published()
        self.assertEqual((outbox.OUTBOX_DIR / record["image"]).read_bytes(), b"d2")  # the chosen design is posted
        sold = self.last_keyboard()[0]
        self.assertEqual([b["text"] for b in sold], ["➖ 1 sold", "➖ 5 sold", "❌ Sold out"])
        outbox.update(record["id"], chat="@shop", message_id=77)  # as publish_telegram.publish records it
        bot.handle(button(sold[1]["callback_data"]))
        self.assertEqual(self.tg_edit.call_args.args[0]["post"]["stock"], 15)
        self.assertIn("Available: 15", self.sent_texts()[-1])
        bot.handle(button(sold[2]["callback_data"]))
        self.assertEqual(outbox.get(record["id"])["post"]["stock"], 0)
        self.assertIn("SOLD OUT", self.sent_texts()[-1])
        self.assertNotIn("reply_markup", self.api.call_args_list[-1].kwargs)  # nothing left to sell

    def test_customer_reserves_from_channel_button(self):
        post_id = outbox.save(dict(POST, stock=4), JPEG)
        outbox.update(post_id, chat="@shop", message_id=9)
        customer = {"id": 555, "first_name": "Anna", "username": "anna_b"}
        bot.handle({"update_id": 6, "message": {"chat": {"id": 555}, "from": customer, "text": f"/start o{post_id}"}})
        amounts = [b["text"] for b in self.last_keyboard()[0]]
        self.assertEqual(amounts, ["1", "2", "3"])  # only what is in stock
        bot.handle({"update_id": 7, "callback_query": {"id": "q", "data": f"order:{post_id}:3", "from": customer,
                                                       "message": {"chat": {"id": 555}}}})
        record = outbox.get(post_id)
        self.assertEqual(record["post"]["stock"], 1)
        self.assertEqual(record["orders"][0]["amount"], 3)
        self.tg_edit.assert_called_once()  # channel post now says Available: 1
        to_customer, to_seller = self.api.call_args_list[-2].kwargs, self.api.call_args_list[-1].kwargs
        self.assertEqual(to_customer["chat_id"], 555)
        self.assertIn("✅ Reserved: 3 ×", to_customer["text"])
        self.assertEqual(to_seller["chat_id"], str(SELLER))
        self.assertIn("tg://user?id=555", to_seller["text"])
        self.assertIn("@anna_b", to_seller["text"])

    def test_customer_cannot_reserve_more_than_stock(self):
        post_id = outbox.save(dict(POST, stock=1), JPEG)
        bot.handle({"update_id": 7, "callback_query": {"id": "q", "data": f"order:{post_id}:2", "from": {"id": 555},
                                                       "message": {"chat": {"id": 555}}}})
        self.assertEqual(self.sent_texts()[-1], "Sorry, only 1 left.")
        self.assertEqual(outbox.get(post_id)["post"]["stock"], 1)

    def test_stranger_message_points_to_channel(self):
        bot.handle({"update_id": 8, "message": {"chat": {"id": 555}, "from": {"id": 555}, "text": "hello"}})
        self.assertIn("🛒 Reserve", self.sent_texts()[-1])

    def test_skip_stock(self):
        draft_id = self.photo_only()
        bot.handle(button(f"type:{draft_id}:0"))
        bot.handle({"update_id": 5, "message": {"chat": {"id": 7}, "from": {"id": SELLER}, "text": "€4"}})
        bot.handle(button(f"stock:{draft_id}:skip"))
        self.assertIsNone(bot.drafts[draft_id]["post"]["stock"])
        self.assertNotIn("Available", self.sent_texts()[-1])

    def test_owner_id_setting_wins_over_owner_file(self):
        with mock.patch.object(publish_telegram, "setting", lambda name: {"OWNER_ID": "999"}.get(name, "")):
            self.assertTrue(bot.allowed(999))
            self.assertFalse(bot.allowed(SELLER))  # SELLER is in owner.txt but OWNER_ID decides


if __name__ == "__main__":
    unittest.main()
