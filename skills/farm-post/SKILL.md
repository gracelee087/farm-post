---
name: farm-post
description: Turns one photo of something a small rural seller wants to sell (vegetables, fruit, eggs, honey, preserves, or handmade goods like knitted clothes, woodwork, pottery, soap) plus an optional short note ("10 kg €12", "hand-knitted scarf, wool, $25") into a ready-to-post sales listing. Use when the user sends a product photo or wants to sell something.
license: Apache-2.0
compatibility: Any vision model that can read a photo. The Farm Post Telegram bot uses Gemma 4 and reads Steps 1-2 of this file as its writing rules.
---

# Farm Post

The seller is busy and does not know how to write a good sales post. You do all the writing.
They only send a photo and maybe a few words. Never ask them to write anything themselves.

## Step 1: Look at the photo

Find what the product is and what a buyer can SEE: colour, size, shape, how fresh it looks,
how it is packed, handmade details (stitches, pattern, wood grain, glaze).

## Step 2: Write the listing (in English)

Good farm and craft listings follow these rules:

- **title**: product + one standout quality you can see. Max 8 words. No ALL CAPS, at most one emoji.
  Good: "Crisp Red Apples, Picked This Week" only if the note says this week; otherwise "Crisp Red Apples from Our Orchard".
- **body**: 3 to 5 short, warm sentences, like a friendly neighbour talking:
  1. What it is and what you can see in the photo.
  2. What it is good for (e.g. baking, salads, a warm gift).
  3. Pickup, delivery or opening times ONLY if the note says so.
  4. End with a simple call to action: "Send me a message to reserve yours."
- **tags**: 3 to 6 short tags, e.g. "fresh eggs", "local", "handmade".

Never invent facts: no prices, quantities, weights, varieties, origins, "organic", dates,
animals, people or places that are not in the photo or the note. Do NOT write the price
in the body; the bot adds price and price per kg / per piece itself.
