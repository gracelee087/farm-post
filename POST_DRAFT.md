---
title: "[TODO title with a measured number, e.g. 'A farm-shop listing in N seconds, on a phone in airplane mode']"
tags: devchallenge, hf26challenge, gemma, opensource
---

<!-- DRAFT. Every [TODO] must be filled with a measured value or removed. Do not publish with TODOs. -->

## What I Built

**Farm Post** is an Agent Skill for small rural sellers — one person or a family selling vegetables,
eggs, honey, jam, or hand-knitted scarves. They take one photo, say a few words
("hand-knitted scarf, wool, 25 dollars"), and get a finished sales listing: title, friendly
description, tags, price and price per kg / per piece. It is saved on the phone and posted to the
shop's Telegram channel as soon as there is internet.

The assumption behind it: these sellers know their products, not marketing copy. So the skill does
all the writing, and the seller never types a sentence.

The model runs **on the phone** (Gemma 4 in Google AI Edge Gallery). No API key, no AI bill,
and the photo never leaves the device for the AI step.

## Demo

[TODO screenshots: photo + voice note -> listing card; same run in airplane mode; Telegram channel post]
[TODO short video]

## Code

[TODO repo link] — the skill lives in `skills/farm-post/` (Agent Skills format: `SKILL.md`,
`scripts/`, `assets/`).

## How I Built It

```
Seller's Android phone · Google AI Edge Gallery (works in airplane mode)
  photo + spoken note "10 kilos for 12 euro"
     -> Gemma 4 (on the phone) looks at the photo, writes title / description / tags
     -> farm-post skill (JavaScript, runs in the app's webview)
          - computes price and unit price from the note in code (the model never makes up a price)
          - saves the listing in an on-phone outbox
          - online + Telegram set up -> posts it to the shop channel
     -> big listing card with a Copy button
```

**How the open-source pieces work**

- **Gemma 4 (Apache 2.0).** The weights are public, so anyone can download the model and run it on
  their own hardware. Google AI Edge Gallery runs the small E2B/E4B variants on the phone itself;
  the model reads the photo and the voice note and follows the instructions in `SKILL.md`.
- **Agent Skills (agentskills.io format).** A skill is a folder: `SKILL.md` (name, description,
  instructions) plus optional scripts and assets. The model only sees the name and description until
  a request matches, then loads the instructions and calls the skill's script with JSON.
- **The writing rules are the product.** `SKILL.md` encodes what a good farm listing looks like:
  product + one visible quality in the title, 3–5 warm sentences, a call to action, and a hard rule
  never to invent prices, weights, origins or "organic".
- **Code does the maths.** In tests the model added things like "a 5 kg bag" or "happy hens" that
  were not in the note (gemma3:4b, laptop benchmark), so prices and unit prices are parsed from the
  seller's own words in JavaScript: `€`, `$`, `£`, `₹`, 3-letter codes, kg / g / lb / l / pieces /
  dozen. Same 12 test cases pass in the JS skill and the Python prototype.

**Measured so far (laptop prototype, CPU only, no GPU, 15.4 GB RAM, Ollama 0.32.15):**

| Model | First listing (incl. model load) | Next listings |
|---|---|---|
| gemma4:e4b | 51.9 s | 14.0 – 28.9 s |
| gemma3:4b | 49.6 s | 13.9 – 45.1 s |

Single runs on 3 sample photos; gemma4:e4b also made fewer unsupported claims, so it is the default.
[TODO phone timings: model, phone, seconds per listing, airplane mode y/n]

**Limits I hit (honest list)**

- The skill's script cannot receive the photo bytes, so the Telegram post is text-only; the seller
  attaches the photo. [TODO confirm on phone]
- In the field, sellers mostly use WhatsApp, not Telegram. WhatsApp's official Cloud API has no way
  to post to Channels or Status, so I chose Telegram (free Bot API) for this prototype.
- The parser needs digits ("25 dollars"); the skill tells Gemma to write spoken numbers as digits.

## Why Does Open Innovation Matter?

[TODO 1 paragraph: a rural seller can't justify a monthly AI subscription or a cloud account for a
few posts a week; open weights + an open skill format mean the whole tool is a free download that
keeps working without signal and without sending product photos to an AI company.]

## My First User

[TODO Hofladen field test, 2026-10-18 — see FIELD_TEST.md: how they post today, how long it takes,
3–5 real products with seconds + correct?, airplane-mode run, quote, "would you pay / how much?"]

## Prize Categories

- **Best Use of Gemma** — Gemma 4 runs on the phone, reads the photo and voice note, and drives the skill.
[TODO add .tech only if the skill is actually hosted on a claimed .tech domain]
