"""Offline tests for server.py. urllib is mocked: no network, no real key."""

import io
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

import server

SAMPLE = {
    "shopping_results": [
        {"title": "Honey 500g", "price": "$10.00", "extracted_price": 10.0, "source": "Shop A"},
        {"title": "Honey 1kg", "price": "$30.00", "extracted_price": 30.0, "source": "Shop B"},
        {"title": "Raw honey", "price": "$20.00", "extracted_price": 20.0, "source": "Shop C"},
        {"title": "Honey jar", "price": "$40.00", "extracted_price": 40.0, "source": "Shop D"},
        {"title": "Comb honey", "price": "$15.00", "extracted_price": 15.0, "source": "Shop E"},
        {"title": "Honey gift", "price": "$25.00", "extracted_price": 25.0, "source": "Shop F"},
    ]
}


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def fake_urlopen(payload):
    return mock.patch.object(
        urllib.request, "urlopen",
        side_effect=lambda *a, **k: FakeResp(json.dumps(payload).encode()),
    )


class Base(unittest.TestCase):
    def setUp(self):
        server.reset_state()
        self.env = mock.patch.dict(os.environ, {"SERPAPI_API_KEY": "dummy-secret-key"})
        self.env.start()

    def tearDown(self):
        self.env.stop()


class SummaryTests(Base):
    def test_summary_math(self):
        body = server.summarize("honey", "us", SAMPLE)
        self.assertEqual(body["count"], 6)
        self.assertEqual(body["min"], 10.0)
        self.assertEqual(body["max"], 40.0)
        self.assertEqual(body["median"], 22.5)
        self.assertEqual(body["currency_hint"], "$")
        self.assertEqual(len(body["examples"]), 5)
        self.assertEqual(body["examples"][0], {"title": "Honey 500g", "price": "$10.00", "source": "Shop A"})

    def test_skips_missing_extracted_price(self):
        data = {"shopping_results": [{"title": "x", "price": "12,99 €"}, {"title": "y", "extracted_price": 5}]}
        body = server.summarize("x", "de", data)
        self.assertEqual((body["count"], body["min"], body["median"], body["max"]), (1, 5.0, 5.0, 5.0))
        self.assertEqual(body["currency_hint"], "€")

    def test_no_results(self):
        body = server.summarize("nothing", "us", {})
        self.assertEqual(body, {
            "query": "nothing", "gl": "us", "count": 0, "min": None, "median": None,
            "max": None, "currency_hint": None, "examples": [],
        })


class PriceTests(Base):
    def test_cache_hit_calls_upstream_once(self):
        with fake_urlopen(SAMPLE) as m:
            s1, b1 = server.handle_price({"q": ["honey"]})
            s2, b2 = server.handle_price({"q": ["  HONEY "], "gl": ["US"]})
        self.assertEqual((s1, s2), (200, 200))
        self.assertEqual(b1, b2)
        self.assertEqual(m.call_count, 1)

    def test_upstream_url_has_params(self):
        with fake_urlopen(SAMPLE) as m:
            server.handle_price({"q": ["sweet potato"], "gl": ["kr"]})
        url = m.call_args[0][0]
        self.assertTrue(url.startswith("https://serpapi.com/search.json?"))
        for part in ("engine=google_shopping", "q=sweet+potato", "gl=kr", "hl=en", "api_key=dummy-secret-key"):
            self.assertIn(part, url)

    def test_daily_limit_429(self):
        with fake_urlopen(SAMPLE) as m:
            for i in range(server.DAILY_LIMIT):
                status, _ = server.handle_price({"q": [f"item {i}"]})
                self.assertEqual(status, 200)
            status, body = server.handle_price({"q": ["one more"]})
            # Cached queries still work after the limit.
            cached_status, _ = server.handle_price({"q": ["item 0"]})
        self.assertEqual(status, 429)
        self.assertIn("error", body)
        self.assertEqual(cached_status, 200)
        self.assertEqual(m.call_count, server.DAILY_LIMIT)

    def test_validation_400(self):
        cases = [{}, {"q": ["   "]}, {"q": ["x" * 101]}, {"q": ["a"], "gl": ["usa"]},
                 {"q": ["a"], "gl": ["1x"]}]
        with fake_urlopen(SAMPLE) as m:
            for qs in cases:
                status, body = server.handle_price(qs)
                self.assertEqual(status, 400, qs)
                self.assertIn("error", body)
        m.assert_not_called()

    def test_missing_key_500(self):
        with mock.patch.dict(os.environ, {"SERPAPI_API_KEY": ""}), fake_urlopen(SAMPLE) as m:
            status, body = server.handle_price({"q": ["honey"]})
        self.assertEqual(status, 500)
        self.assertIn("SERPAPI_API_KEY is not set", body["error"])
        m.assert_not_called()

    def test_upstream_error_does_not_leak_key(self):
        err = urllib.error.HTTPError("https://serpapi.com/search.json?api_key=dummy-secret-key",
                                     401, "Unauthorized", {}, None)
        with mock.patch.object(urllib.request, "urlopen", side_effect=err):
            status, body = server.handle_price({"q": ["honey"]})
        self.assertEqual(status, 502)
        self.assertNotIn("dummy-secret-key", json.dumps(body))


class HttpTests(Base):
    def setUp(self):
        super().setUp()
        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def get(self, path):
        # Uses the real urlopen against localhost, captured before any mocking.
        try:
            resp = REAL_URLOPEN(f"http://127.0.0.1:{self.port}{path}", timeout=5)
        except urllib.error.HTTPError as e:
            resp = e
        return resp.status, resp.headers, resp.read()

    def test_cors_on_all_responses(self):
        for path in ("/health", "/price", "/nope"):
            _, headers, _ = self.get(path)
            self.assertEqual(headers["Access-Control-Allow-Origin"], "*", path)

    def test_health(self):
        status, _, body = self.get("/health")
        self.assertEqual((status, body), (200, b"ok"))

    def test_price_over_http(self):
        with fake_urlopen(SAMPLE):
            status, headers, body = self.get("/price?q=honey&gl=us")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")
        data = json.loads(body)
        self.assertEqual(data["count"], 6)
        self.assertNotIn("dummy-secret-key", body.decode())


REAL_URLOPEN = urllib.request.urlopen

if __name__ == "__main__":
    unittest.main()
