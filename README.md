# Farm Post

One photo + a few spoken words → a finished sales listing, written by Gemma running **on the phone**.
For small rural sellers (one person or a family): vegetables, eggs, honey, jam, hand-knitted goods.

Built for the DEV Hacktoberfest Open-Source AI Challenge, Week 2 "Side Hustle".

## The skill (main product)

`skills/farm-post/` is an [Agent Skill](https://agentskills.io/specification) for
[Google AI Edge Gallery](https://github.com/google-ai-edge/gallery) with Gemma 4 E2B/E4B:

| File | What it does |
|---|---|
| `SKILL.md` | Instructions for the on-device model, including the rules of a good farm listing |
| `scripts/listing.js` | Price + price per kg/piece parsed from the seller's note (not by the model), on-phone outbox, Telegram posting |
| `scripts/index.html` | Entry point called by the app (`create`, `publish`, `list`) |
| `assets/card.html` | Large listing card with a Copy button |

Install on Android: copy `skills/farm-post/` to the phone → Gallery → Agent Skills → Skills → **+** →
**Import local skill**. Optional: enter `BOT_TOKEN @channel` when asked, to post to a Telegram channel.

## Laptop prototype (v0)

Python + [Ollama](https://ollama.com) + Streamlit, same idea on a laptop:
`generate.py` (Gemma via Ollama), `app.py` (Streamlit UI), `bot.py` (Telegram bot), `outbox.py`,
`publish_site.py`, `publish_telegram.py`. Benchmark: `bench.md`.

```
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
ollama pull gemma4:e4b
.venv\Scripts\python -m streamlit run app.py
```

## Tests

```
node --test tests/listing.test.js
python -m unittest discover -s tests
```

## Licenses

Code: Apache-2.0 (`LICENSE`). Gemma 4: Apache-2.0. Sample photos: see `samples/SOURCES.md`
(CC BY 4.0, CC BY-SA 2.0, public domain).
