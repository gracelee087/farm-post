---
title: "Farm Post: a phone-only AI that writes the sales post for small farm and craft sellers"
tags: devchallenge, hf26challenge, gemma, opensource
---

<!-- DRAFT. Every [TODO] must be filled with a measured value or removed. Do not publish with TODOs. -->

## What I Built

**Farm Post** is an Agent Skill for small rural sellers: one person or a family selling vegetables,
eggs, honey, jam, or hand-knitted scarves. They take one photo, say a few words
("hand-knitted scarf, wool, 25 dollars"), and get a finished sales listing: a title, a friendly
description, tags, the price and the price per kg or per piece. The listing is saved on the phone
and posted to the shop's Telegram channel as soon as there is internet.

The idea behind it is simple. These sellers know their products, not marketing copy, so the skill
does all the writing and the seller never has to type a sentence.

It also answers the two questions a small seller has after posting:

- **"How many do I have left?"** Say "sold 3 scarves" or "eggs are sold out". The skill updates the
  count and edits the post that is already in the Telegram channel, so it shows "Available: 2" or
  "❌ SOLD OUT".
- **"What should I charge?"** The skill looks up what online shops charge for similar items
  (SerpApi Google Shopping) and gives a range. It is only a rough guide; the skill never changes
  the seller's own price.

The model runs **on the phone** (Gemma 4 in Google AI Edge Gallery). There is no API key and no AI
bill, and the photo never leaves the phone for the AI step.

## Demo

[TODO screenshots: photo + voice note -> listing card; same run in airplane mode; Telegram channel post; "sold out" edit]
[TODO short video]

Live Telegram demo channel: https://t.me/demofarmshop_lee

## Code

https://github.com/gracelee087/farm-post

- `skills/farm-post/` is the skill itself, in the Agent Skills format: `SKILL.md`, `scripts/`, `assets/`.
- `price-proxy/` is a small market-price server deployed on Render.
- The repo root also holds a laptop prototype (Ollama + Streamlit + a Telegram bot) that I used to
  test prompts and measure speed.

## How I Built It

```
Seller's Android phone · Google AI Edge Gallery
  photo + spoken note "10 kilos for 12 euro"
     -> Gemma 4 (on the phone) looks at the photo, writes title / description / tags
     -> farm-post skill (JavaScript, runs inside the app)
          - computes price and unit price from the note in code (the model never makes up a price)
          - saves the listing in an outbox on the phone
          - online + Telegram set up -> posts it to the shop channel
          - "sold 3" / "sold out" -> updates stock and edits the channel post
          - "what should I charge?" -> asks the price proxy (Render) -> SerpApi Google Shopping
     -> big listing card with a Copy button
```

**How the open-source pieces work**

- **Gemma 4 (Apache 2.0).** The weights are public, so anyone can download the model and run it on
  their own hardware. Google AI Edge Gallery runs the small E2B and E4B versions on the phone itself.
  The model reads the photo and the voice note and follows the instructions in `SKILL.md`.
- **Agent Skills (agentskills.io format).** A skill is a folder: `SKILL.md` (name, description,
  instructions) plus optional scripts and assets. The model sees only the name and description until
  a request matches. Then it loads the instructions and calls the skill's script with JSON.
- **The writing rules are the product.** `SKILL.md` describes what a good farm listing looks like:
  - the title is the product plus one quality you can see in the photo;
  - the description is 3–5 warm sentences ending with a call to action;
  - the model must never invent prices, weights, origins or "organic".
- **Code does the maths.** In my tests the model added details that were not in the note, such as
  "a 5 kg bag" or "happy hens" (gemma3:4b, laptop benchmark). So prices and unit prices are parsed
  from the seller's own words in JavaScript. The parser understands:
  - currency symbols `€`, `$`, `£`, `₹`, currency words and 3-letter codes;
  - units kg, g, lb, l, pieces and dozen.

  The same 12 test cases pass in the JS skill and in the Python prototype.

**Two small servers, both free**

- **Telegram.** The skill posts straight from the phone with the Bot API, so no server is needed.
  Telegram rejects the browser's CORS preflight but accepts a plain form-encoded POST, so that is
  what the skill sends. To change the stock it calls `editMessageText` on the message it already posted.
- **Market price.** SerpApi does not allow calls from a browser, which protects the API key. So the
  phone calls a 185-line Python server (standard library only) on Render's free plan, and that server holds the key and
  calls SerpApi. It caches answers for an hour and stops at 200 lookups a day so a free key can't
  be drained.

  A real lookup for "hand knitted wool scarf" in the US returned 40 offers:

  | Lowest | Typical | Highest |
  |---|---|---|
  | $17.59 | $55.19 | $189.00 |

  The examples included Etsy and eBay listings.

**Measured so far (laptop prototype, CPU only, no GPU, 15.4 GB RAM, Ollama 0.32.15):**

| Model | First listing (incl. model load) | Next listings |
|---|---|---|
| gemma4:e4b | 51.9 s | 14.0 – 28.9 s |
| gemma3:4b | 49.6 s | 13.9 – 45.1 s |

These are single runs on 3 sample photos. gemma4:e4b also made fewer unsupported claims, so it is
the default.
[TODO phone timings: model, phone, seconds per listing, airplane mode y/n]

**Limits I hit (honest list)**

- The skill's script cannot receive the photo itself, so the Telegram post is text only and the
  seller attaches the photo. [TODO confirm on phone]
- Many small sellers use WhatsApp, not Telegram. WhatsApp's official Cloud API has no way to post
  to Channels or Status, so I chose Telegram (free Bot API) for this prototype.
- The price parser needs digits ("25 dollars"), so the skill tells Gemma to write spoken numbers as digits.
- Online-shop prices are not farm-gate prices. The skill says so every time it shows them.
- The free Render server sleeps when idle, so the first price lookup after a break can take about a minute.

## Why Does Open Innovation Matter?

[TODO 1 paragraph, user's own words. Points: a rural seller can't justify a monthly AI subscription
or a cloud account for a few posts a week; open weights + an open skill format mean the whole tool
is a free download that keeps working without signal and without sending product photos to an AI company.]

## My Agent Session

[TODO optional. I built this with Claude Code and split the work across sub-agents (skill core,
UI, research, price proxy). Add 1–2 concrete moments, e.g. checking Telegram's CORS behaviour with
curl before writing the posting code.]

## My First User

[TODO Hofladen field test, 2026-10-18 (see FIELD_TEST.md):
- how they post today and how long it takes;
- 3–5 real products, with seconds per listing and whether the listing was correct;
- an airplane-mode run;
- a quote;
- "would you pay, and how much?"]

## Prize Categories

- **Best Use of Gemma.** Gemma 4 runs on the phone, reads the photo and the voice note, and drives the skill.
- **SerpApi.** It gives the agent live Google Shopping prices for "what should I charge?".
- **Render.** The price proxy that keeps the SerpApi key off the phone is deployed on Render's free plan.
