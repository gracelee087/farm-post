"""Photo + short note -> English sales listing for a small rural business, via a local Gemma model (Ollama)."""
import base64
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/chat"
# Same open model in Google's cloud (free tier): used when GEMINI_API_KEY is set, so no computer has to stay on.
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
CLOUD_MODEL = "gemma-4-26b-a4b-it"
SKILL_FILE = Path(__file__).parent / "skills" / "farm-post" / "SKILL.md"


def listing_rules(skill_text: str) -> str:
    """Steps 1-2 of SKILL.md, so the bot and the phone skill follow the same listing rules."""
    return skill_text.split("## Step 1", 1)[1].split("## Step 3", 1)[0].strip()


PROMPT = """You write sales listings for a small rural business run by one person or a family
anywhere in the world. Products can be anything they grow or make: farm produce, eggs, honey,
preserves, or handmade goods such as knitted clothes, woodwork, pottery or soap.
Look at the photo and read the seller's note, then follow these rules:

## Step 1""" + listing_rules(SKILL_FILE.read_text(encoding="utf-8")) + """

If you mention a quantity, use exactly the number from the note.
Reply with ONLY a JSON object with these keys:
"item": what the product is, in a few English words,
"title": the listing title,
"body": the listing description,
"tags": list of tag strings,
"search": 2-4 English words to look up similar products in online shops, e.g. "hand knitted wool scarf".

Seller's note: """

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


def _post_json(url: str, payload: dict, headers: dict, name: str) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{name} error {e.code}: {e.read().decode('utf-8', 'replace')[:500]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach {name}: {e.reason}") from e


def _ask_ollama(prompt: str, image_b64: str, model: str) -> str:
    payload = {"model": model, "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
               "format": "json", "stream": False, "think": False}
    return _post_json(OLLAMA_URL, payload, {}, "Ollama").get("message", {}).get("content", "")


def _ask_gemini(prompt: str, image_b64: str, mime: str, model: str, key: str) -> str:
    payload = {"contents": [{"parts": [{"inline_data": {"mime_type": mime, "data": image_b64}}, {"text": prompt}]}]}
    reply = _post_json(GEMINI_URL.format(model=model), payload, {"x-goog-api-key": key}, "Gemini API")
    parts = reply.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))  # skip thinking parts


def generate_post(image_bytes: bytes, note: str, model: str = "") -> dict:
    """Cloud Gemma if GEMINI_API_KEY is set (env or .env), else local Gemma via Ollama."""
    from publish_telegram import setting  # reads env, then farm-post/.env

    prompt = PROMPT + (note.strip() or "(no note)")
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    key = setting("GEMINI_API_KEY")
    start = time.time()
    if key:
        model = model or setting("GEMMA_MODEL") or CLOUD_MODEL
        mime = "image/png" if image_bytes.startswith(b"\x89PNG") else "image/jpeg"
        text = _ask_gemini(prompt, image_b64, mime, model, key)
    else:
        model = model or "gemma4:e4b"
        text = _ask_ollama(prompt, image_b64, model)
    seconds = time.time() - start

    data = _parse_json(text)
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
        "search": str(data.get("search", "")).strip(),
        "model": model,
        "seconds": round(seconds, 2),
    }


if __name__ == "__main__":
    import argparse

    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Generate a farm-shop listing from a photo and a note.")
    ap.add_argument("image")
    ap.add_argument("note")
    ap.add_argument("--model", default="")
    args = ap.parse_args()
    with open(args.image, "rb") as f:
        result = generate_post(f.read(), args.note, args.model)
    print(json.dumps(result, ensure_ascii=False, indent=2))
