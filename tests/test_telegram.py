import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import outbox  # noqa: E402
import publish_telegram  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0fake-jpeg"
POST = {"title": "Fresh potatoes <from the farm>", "body": "Tasty.", "price_text": "€12.00",
        "unit_price_text": "€1.20/kg", "tags": ["potatoes", "#local food"]}


def _reply(ok=True):
    return io.BytesIO(json.dumps({"ok": ok, "description": "Bad Request"}).encode())


class TelegramTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for patcher in (mock.patch.object(outbox, "OUTBOX_DIR", Path(tmp.name) / "outbox"),
                        mock.patch.object(publish_telegram, "ENV_FILE", Path(tmp.name) / ".env"),
                        mock.patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "T", "TELEGRAM_CHANNEL": "@shop"})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_caption_escapes_and_fits_limit(self):
        text = publish_telegram.caption({**POST, "body": "x" * 5000})
        self.assertIn("<b>Fresh potatoes &lt;from the farm&gt;</b>", text)
        self.assertIn("€12.00 · €1.20/kg", text)
        self.assertIn("#potatoes #localfood", text)
        self.assertLessEqual(len(text), publish_telegram.CAPTION_LIMIT)

    def test_publish_sends_photo_and_marks_published(self):
        post_id = outbox.save(POST, JPEG)
        with mock.patch("urllib.request.urlopen", return_value=_reply()) as urlopen:
            publish_telegram.publish(outbox.pending())
        req = urlopen.call_args.args[0]
        self.assertEqual(req.full_url, "https://api.telegram.org/botT/sendPhoto")
        self.assertIn(b'name="chat_id"\r\n\r\n@shop', req.data)
        self.assertIn(JPEG, req.data)
        self.assertEqual(outbox.published()[0]["id"], post_id)

    def test_failure_keeps_unsent_pending_and_sent_published(self):
        outbox.save(POST, JPEG)
        outbox.save(POST, JPEG)
        with mock.patch("urllib.request.urlopen", side_effect=[_reply(), _reply(ok=False)]):
            with self.assertRaises(RuntimeError):
                publish_telegram.publish(outbox.pending())
        self.assertEqual((len(outbox.published()), len(outbox.pending())), (1, 1))

    def test_publish_remembers_message_and_edit_rewrites_caption(self):
        post_id = outbox.save({**POST, "stock": 3}, JPEG)
        ok = io.BytesIO(json.dumps({"ok": True, "result": {"message_id": 55}}).encode())
        with mock.patch("urllib.request.urlopen", return_value=ok):
            publish_telegram.publish(outbox.pending())
        record = outbox.get(post_id)
        self.assertEqual((record["chat"], record["message_id"]), ("@shop", 55))
        record = outbox.update(post_id, post={**record["post"], "stock": 0})
        with mock.patch("urllib.request.urlopen", return_value=_reply()) as urlopen:
            publish_telegram.edit(record)
        req = urlopen.call_args.args[0]
        self.assertTrue(req.full_url.endswith("/editMessageCaption"))
        self.assertIn("SOLD OUT", json.loads(req.data)["caption"])

    def test_not_configured(self):
        with mock.patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHANNEL": ""}):
            self.assertFalse(publish_telegram.configured())
            with self.assertRaises(RuntimeError):
                publish_telegram.publish([])


if __name__ == "__main__":
    unittest.main()
