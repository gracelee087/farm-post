"""Tiny SerpApi price proxy for the farm-post on-phone Agent Skill.

The browser cannot call SerpApi directly (CORS, and the key would leak), so
this server holds SERPAPI_API_KEY and returns a small price summary.

Standard library only. Run: SERPAPI_API_KEY=... PORT=8000 python server.py
"""

import json
import os
import re
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERPAPI_URL = "https://serpapi.com/search.json"
CACHE_TTL_SECONDS = 3600
DAILY_LIMIT = 200
MAX_Q_LEN = 100
MAX_EXAMPLES = 5
UPSTREAM_TIMEOUT = 20

_GL_RE = re.compile(r"^[a-z]{2}$")
_HL_RE = re.compile(r"^[a-z]{2}(-[a-z]{2})?$")
_SYMBOL_RE = re.compile(r"[^\d\s.,+\-]+")

_lock = threading.Lock()
_cache = {}  # (q_lower, gl, hl) -> (expires_at, payload)
_usage = {"day": None, "calls": 0}


def reset_state():
    """Clear cache and daily counter (used by tests)."""
    with _lock:
        _cache.clear()
        _usage["day"] = None
        _usage["calls"] = 0


def _take_daily_slot():
    """Reserve one upstream call for today (UTC). False if the limit is reached."""
    today = datetime.now(timezone.utc).date().isoformat()
    with _lock:
        if _usage["day"] != today:
            _usage["day"] = today
            _usage["calls"] = 0
        if _usage["calls"] >= DAILY_LIMIT:
            return False
        _usage["calls"] += 1
        return True


def currency_hint(price_str):
    """'$829.00' -> '$', '12,99 €' -> '€', None/'' -> None."""
    if not price_str:
        return None
    m = _SYMBOL_RE.search(price_str)
    return m.group(0) if m else None


def summarize(query, gl, data):
    """Build the response body from a SerpApi google_shopping JSON response.

    Field names per https://serpapi.com/google-shopping-api : each item in
    `shopping_results` has `title`, `source`, `price` (display string such as
    "$829.00") and `extracted_price` (number such as 829.0).
    """
    results = data.get("shopping_results") or []
    prices = [
        float(r["extracted_price"])
        for r in results
        if isinstance(r.get("extracted_price"), (int, float))
        and not isinstance(r.get("extracted_price"), bool)
    ]
    examples = [
        {"title": r.get("title"), "price": r.get("price"), "source": r.get("source")}
        for r in results[:MAX_EXAMPLES]
    ]
    return {
        "query": query,
        "gl": gl,
        "count": len(prices),
        "min": min(prices) if prices else None,
        "median": statistics.median(prices) if prices else None,
        "max": max(prices) if prices else None,
        "currency_hint": currency_hint(results[0].get("price")) if results else None,
        "examples": examples,
    }


def fetch_shopping(query, gl, hl, api_key):
    params = urllib.parse.urlencode({
        "engine": "google_shopping",
        "q": query,
        "gl": gl,
        "hl": hl,
        "api_key": api_key,
    })
    with urllib.request.urlopen(f"{SERPAPI_URL}?{params}", timeout=UPSTREAM_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def handle_price(qs):
    """Return (status, body_dict) for GET /price."""
    query = " ".join((qs.get("q", [""])[0]).split())
    gl = qs.get("gl", ["us"])[0].strip().lower()
    hl = qs.get("hl", ["en"])[0].strip().lower()

    if not query:
        return 400, {"error": "q is required"}
    if len(query) > MAX_Q_LEN:
        return 400, {"error": f"q must be at most {MAX_Q_LEN} characters"}
    if not _GL_RE.match(gl):
        return 400, {"error": "gl must be a 2-letter country code"}
    if not _HL_RE.match(hl):
        return 400, {"error": "hl must be a language code like 'en'"}

    key = (query.lower(), gl, hl)
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return 200, hit[1]

    api_key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not api_key:
        return 500, {"error": "server misconfigured: SERPAPI_API_KEY is not set"}

    if not _take_daily_slot():
        return 429, {"error": f"daily limit of {DAILY_LIMIT} upstream searches reached, try again tomorrow (UTC)"}

    try:
        data = fetch_shopping(query, gl, hl, api_key)
    except urllib.error.HTTPError as e:
        # Do not echo the exception text or URL: the URL contains the key.
        return 502, {"error": f"upstream error (HTTP {e.code})"}
    except (urllib.error.URLError, TimeoutError, ValueError):
        return 502, {"error": "upstream unavailable"}

    body = summarize(query, gl, data)
    with _lock:
        _cache[key] = (now + CACHE_TTL_SECONDS, body)
    return 200, body


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, content_type="application/json"):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self._send(204, b"", "text/plain")

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if url.path == "/health":
            self._send(200, b"ok", "text/plain")
        elif url.path == "/price":
            status, body = handle_price(urllib.parse.parse_qs(url.query))
            self._send(status, body)
        else:
            self._send(404, {"error": "not found"})


def main():
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"price-proxy listening on 0.0.0.0:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
