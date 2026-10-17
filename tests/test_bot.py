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
                  mock.patch.object(bot, "download_photo", return_value=JPEG),
                  mock.patch.object(bot, "generate_post", return_value=dict(POST))):
            p.start()
            self.addCleanup(p.stop)
        self.api = mock.patch.object(bot, "api").start()
        self.tg_publish = mock.patch.object(publish_telegram, "publish").start()
        self.addCleanup(mock.patch.stopall)
        bot.drafts.clear()

    def sent_texts(self):
        return [c.kwargs.get("text", "") for c in self.api.call_args_list if c.args[0] == "sendMessage"]

    def test_photo_gives_draft_with_buttons(self):
        bot.handle(photo_update())
        bot.download_photo.assert_called_once_with("big")
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
        self.assertIn("private", self.sent_texts()[-1])

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

    def test_owner_id_setting_wins_over_owner_file(self):
        with mock.patch.object(publish_telegram, "setting", lambda name: {"OWNER_ID": "999"}.get(name, "")):
            self.assertTrue(bot.allowed(999))
            self.assertFalse(bot.allowed(SELLER))  # SELLER is in owner.txt but OWNER_ID decides


if __name__ == "__main__":
    unittest.main()
