import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import outbox  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0fake-jpeg"
POST = {
    "item": "Potatoes", "title": "Fresh potatoes <from the farm>", "body": "Tasty.\nFirm when cooked.",
    "price_text": "€12.00", "unit_price_text": "€1.20/kg", "tags": ["potatoes", "#regional"],
    "model": "gemma4:e4b", "seconds": 1.0,
}


class OutboxTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(outbox, "OUTBOX_DIR", Path(tmp.name) / "outbox")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_save_creates_pending_record_and_image(self):
        post_id = outbox.save(POST, JPEG)
        [record] = outbox.pending()
        self.assertEqual(record["id"], post_id)
        self.assertEqual(record["status"], "pending")
        self.assertEqual(record["post"]["title"], POST["title"])
        self.assertEqual((outbox.OUTBOX_DIR / record["image"]).read_bytes(), JPEG)
        self.assertTrue(record["image"].endswith(".jpg"))

    def test_mark_published(self):
        post_id = outbox.save(POST, JPEG)
        outbox.mark_published(post_id)
        self.assertEqual(outbox.pending(), [])
        self.assertEqual(outbox.published()[0]["id"], post_id)

    def test_pending_empty_without_dir(self):
        self.assertEqual(outbox.pending(), [])

    def test_flush_offline_does_nothing(self):
        outbox.save(POST, JPEG)
        publisher = mock.Mock()
        with mock.patch.object(outbox, "is_online", return_value=False):
            self.assertEqual(outbox.flush(publisher), 0)
        publisher.assert_not_called()
        self.assertEqual(len(outbox.pending()), 1)

    def test_flush_online_publishes_all(self):
        outbox.save(POST, JPEG)
        outbox.save(POST, JPEG)
        publisher = mock.Mock()
        with mock.patch.object(outbox, "is_online", return_value=True):
            self.assertEqual(outbox.flush(publisher), 2)
        self.assertEqual(len(publisher.call_args.args[0]), 2)
        self.assertEqual(outbox.pending(), [])

    def test_flush_keeps_pending_when_publisher_fails(self):
        outbox.save(POST, JPEG)
        with mock.patch.object(outbox, "is_online", return_value=True):
            with self.assertRaises(RuntimeError):
                outbox.flush(mock.Mock(side_effect=RuntimeError))
        self.assertEqual(len(outbox.pending()), 1)

    def test_is_online_false_on_connection_error(self):
        with mock.patch("socket.create_connection", side_effect=OSError):
            self.assertFalse(outbox.is_online())


if __name__ == "__main__":
    unittest.main()
