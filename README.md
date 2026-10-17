# Farm Post

One photo → a finished sales post in the farm's Telegram channel, with a Reserve button.
For small rural sellers (one person or a family): vegetables, fruit, eggs, honey, jam, hand-knitted goods.

Built for the DEV Hacktoberfest Open-Source AI Challenge, Week 2 "Side Hustle".

## How it works

1. The seller sends a photo to the Farm Post bot on Telegram.
2. Gemma 4 reads the photo and writes the title, text, tags and a search query (`generate.py`).
3. Online prices for that query (SerpApi, via `price-proxy/`) are shown; the seller taps a price, unit and stock.
4. Four designs are drawn from the real photo (`design.py`); the seller picks one and taps Post.
5. Customers tap 🛒 Reserve under the post, choose an amount, and pay at pickup. Stock goes down and the seller gets a message.

The writing rules live in `skills/farm-post/SKILL.md` ([Agent Skills](https://agentskills.io/specification) format).
The bot reads its Steps 1-2 as Gemma's instructions, so anyone can change how listings are written by editing that file.

## Files

| File | What it does |
|---|---|
| `bot.py` | Telegram bot (polling, or `--webhook` on a server) |
| `generate.py` | Gemma 4 via the Gemini API (`GEMINI_API_KEY`), or local [Ollama](https://ollama.com) `gemma4:e4b` without a key |
| `design.py` | Four listing designs from the seller's photo (Pillow, fonts in `fonts/`) |
| `publish_telegram.py` | Posts and edits channel posts, Reserve button |
| `outbox.py` | Saves listings and orders on disk |
| `price-proxy/` | Small server that calls SerpApi; `render.yaml` deploys it and the bot on Render |

## Run

```
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python bot.py
```

Settings go in `.env`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL`, `GEMINI_API_KEY` (optional, else Ollama), `OWNER_ID` (on a server).

## Tests

```
python -m unittest discover -s tests
```

## Licenses

Code: Apache-2.0 (`LICENSE`). Gemma 4: Apache-2.0. Fonts: see `fonts/`. Sample photos: see `samples/SOURCES.md`
(CC BY 4.0, CC BY-SA 2.0, public domain).
