"""Photo + short note -> English sales listing for a small rural business, via a local Gemma model (Ollama)."""
import base64
import json
import re
import sys
import time
import urllib.error
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/chat"

PROMPT = """You write sales listings for a small rural business run by one person or a family
anywhere in the world. Products can be anything they grow or make: farm produce, eggs, honey,
preserves, or handmade goods such as knitted clothes, woodwork, pottery or soap.
Look at the photo and read the seller's note. Reply with ONLY a JSON object with these keys:
"item": what the product is, in a few English words,
"title": a short, catchy English listing title (max 8 words),
"body": a friendly English description, 3-6 sentences,
"tags": 3-6 short English tags (list of strings).
Rules: use only facts visible in the photo or stated in the note. Do not invent prices,
quantities, weights, varieties, origins, organic claims or dates. If you mention a quantity,
use exactly the number from the note. Do not describe animals, people or places that are not
in the photo or note. Do not mention prices in the body; they are shown separately.

Seller's note: {note}"""

NUM = r"(\d+(?:[.,]\d+)?)"
# Currency symbols and words -> how the price is written. A 3-letter code (e.g. "500 KES") also works.
SYMBOLS = "€$£₹¥₱₦₩₺₫₴₪"
WORDS = {"eur": "€", "euro": "€", "euros": "€", "usd": "$", "dollar": "$", "dollars": "$",
         "gbp": "£", "pound": "£", "pounds": "£", "inr": "₹", "rupee": "₹", "rupees": "₹"}
PRICE_RE = re.compile(rf"(?:([{SYMBOLS}])\s*{NUM})|(?:{NUM}\s*(?:([{SYMBOLS}])|([A-Za-z]{{3,7}})\b))")
QTY_RE = re.compile(rf"{NUM}\s*(kg|g|lb|lbs|ml|l|liter|litre|pieces|piece|pcs|eggs|egg|dozen)\b", re.I)
PIECE = ("piece", 1)
UNITS = {"kg": ("kg", 1), "g": ("kg", 1000), "lb": ("lb", 1), "lbs": ("lb", 1), "l": ("l", 1),
         "liter": ("l", 1), "litre": ("l", 1), "ml": ("l", 1000), "pieces": PIECE, "piece": PIECE,
         "pcs": PIECE, "eggs": PIECE, "egg": PIECE, "dozen": ("piece", 1 / 12)}


def _num(s):
    # "1,000" -> 1000 (thousands separator), "3,50" -> 3.5 (decimal comma)
    if re.fullmatch(r"\d+,\d{3}", s):
        return float(s.replace(",", ""))
    return float(s.replace(",", "."))


def _find_price(note):
    """Return (amount, currency) for the first price in the note, or None."""
    for m in PRICE_RE.finditer(note):
        if m.group(1):
            return _num(m.group(2)), m.group(1)
        if m.group(4):
            return _num(m.group(3)), m.group(4)
        word = m.group(5)
        if word.lower() in WORDS:
            return _num(m.group(3)), WORDS[word.lower()]
        if len(word) == 3 and word.isupper():
            return _num(m.group(3)), word + " "
    return None


def parse_price(note):
    """Return (price_text, unit_price_text) computed from the note only."""
    found = _find_price(note)
    if not found:
        return "", ""
    price, cur = found
    price_text = f"{cur}{price:.2f}"
    q = QTY_RE.search(note)
    if not q or _num(q.group(1)) == 0:
        return price_text, ""
    unit, factor = UNITS[q.group(2).lower()]
    per_unit = price / (_num(q.group(1)) / factor)
    return price_text, f"{cur}{per_unit:.2f}/{unit}"


def _parse_json(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    raise ValueError(f"Model did not return valid JSON: {text[:500]!r}")


def generate_post(image_bytes: bytes, note: str, model: str = "gemma4:e4b") -> dict:
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": PROMPT.format(note=note.strip() or "(no note)"),
            "images": [base64.b64encode(image_bytes).decode("ascii")],
        }],
        "format": "json",
        "stream": False,
        "think": False,
    }
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            reply = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Ollama error {e.code}: {e.read().decode('utf-8', 'replace')}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach Ollama at {OLLAMA_URL}: {e.reason}") from e
    seconds = time.time() - start

    data = _parse_json(reply.get("message", {}).get("content", ""))
    tags = data.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    price_text, unit_price_text = parse_price(note)
    return {
        "item": str(data.get("item", "")).strip(),
        "title": str(data.get("title", "")).strip(),
        "body": str(data.get("body", "")).strip(),
        "price_text": price_text,
        "unit_price_text": unit_price_text,
        "tags": [str(t).strip() for t in tags],
        "model": model,
        "seconds": round(seconds, 2),
    }


if __name__ == "__main__":
    import argparse

    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Generate a farm-shop listing from a photo and a note.")
    ap.add_argument("image")
    ap.add_argument("note")
    ap.add_argument("--model", default="gemma4:e4b")
    args = ap.parse_args()
    with open(args.image, "rb") as f:
        result = generate_post(f.read(), args.note, args.model)
    print(json.dumps(result, ensure_ascii=False, indent=2))
