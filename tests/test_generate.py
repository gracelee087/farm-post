import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import generate  # noqa: E402
import publish_telegram  # noqa: E402

LISTING = {"item": "scarf", "title": "Warm Scarf", "body": "Soft wool.", "tags": ["wool"], "search": "wool scarf"}


def reply(body: dict):
    r = mock.MagicMock()
    r.__enter__.return_value.read.return_value = json.dumps(body).encode()
    return r


class GenerateTest(unittest.TestCase):
    def test_prompt_uses_skill_rules(self):
        self.assertIn("Never invent facts", generate.PROMPT)
        self.assertNotIn("run_js", generate.PROMPT)  # step 3 (phone script) is left out

    def test_cloud_gemma_when_key_is_set(self):
        gemini = {"candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True},
                                                        {"text": json.dumps(LISTING)}]}}]}
        with mock.patch.object(publish_telegram, "setting", lambda n: {"GEMINI_API_KEY": "K"}.get(n, "")), \
                mock.patch("urllib.request.urlopen", return_value=reply(gemini)) as urlopen:
            post = generate.generate_post(b"\xff\xd8jpeg", "scarf $25")
        req = urlopen.call_args.args[0]
        self.assertIn("gemma-4-26b-a4b-it:generateContent", req.full_url)
        self.assertEqual(req.get_header("X-goog-api-key"), "K")
        self.assertEqual(json.loads(req.data)["contents"][0]["parts"][0]["inline_data"]["mime_type"], "image/jpeg")
        self.assertEqual((post["title"], post["price_text"], post["search"]), ("Warm Scarf", "$25.00", "wool scarf"))
        self.assertEqual(post["model"], "gemma-4-26b-a4b-it")

    def test_busy_cloud_retries_then_other_model(self):
        busy = RuntimeError('Gemini API error 503: {"error": {"status": "UNAVAILABLE"}}')
        with mock.patch.object(generate, "_ask_gemini", side_effect=[busy, busy, json.dumps(LISTING)]) as ask, \
                mock.patch("time.sleep"):
            text, model = generate._ask_gemini_retry("p", "img", "image/jpeg", "gemma-4-26b-a4b-it", "K")
        self.assertEqual(model, "gemma-4-31b-it")
        self.assertEqual(ask.call_count, 3)

    def test_bad_request_is_not_retried(self):
        bad = RuntimeError("Gemini API error 400: bad image")
        with mock.patch.object(generate, "_ask_gemini", side_effect=[bad]) as ask, mock.patch("time.sleep"):
            with self.assertRaises(RuntimeError):
                generate._ask_gemini_retry("p", "img", "image/jpeg", "gemma-4-26b-a4b-it", "K")
        self.assertEqual(ask.call_count, 1)

    def test_local_ollama_without_key(self):
        with mock.patch.object(publish_telegram, "setting", lambda n: ""), \
                mock.patch("urllib.request.urlopen", return_value=reply({"message": {"content": json.dumps(LISTING)}})) as urlopen:
            post = generate.generate_post(b"\xff\xd8jpeg", "")
        self.assertEqual(urlopen.call_args.args[0].full_url, generate.OLLAMA_URL)
        self.assertEqual(post["model"], "gemma4:e4b")


if __name__ == "__main__":
    unittest.main()
