---
name: farm-post
description: Turns one photo of something a small rural seller wants to sell (vegetables, fruit, eggs, honey, preserves, or handmade goods like knitted clothes, woodwork, pottery, soap) plus an optional short note ("10 kg €12", "hand-knitted scarf, wool, $25") into a ready-to-post sales listing, saves it on the phone, and posts it to the seller's Telegram channel when there is internet. Use when the user sends a product photo, wants to sell something, or asks to post or show their listings.
license: Apache-2.0
compatibility: Google AI Edge Gallery (Agent Skills) with a vision model such as Gemma 4 E2B/E4B. Works offline; internet only needed to post to Telegram.
metadata:
  require-secret: true
  require-secret-description: Optional. To post automatically, enter your Telegram bot token and channel separated by a space, e.g. "123456:ABC... @myfarmshop". Leave empty to only create and copy listings.
---

# Farm Post

The seller is busy and does not know how to write a good sales post. You do all the writing.
They only send a photo and maybe a few words, typed or SPOKEN (voice recording). Never ask them
to write anything themselves.

If they speak, listen and use what they said as the note: write it down in English, with
numbers as digits and the currency as a word or symbol ("twenty-five dollars" -> "25 dollars",
"ten kilos for twelve euro" -> "10 kg 12 euro").

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
in the body; the script adds price and price per kg / per piece itself.

## Step 3: Save and post

Call the `run_js` tool with:
- **script name**: `index.html`
- **data**: A JSON string with:
  - `action`: "create"
  - `title`: String
  - `body`: String
  - `tags`: Array of strings
  - `note`: String. The seller's own words (typed, or written down from their voice as above),
    with every number and price they gave. "" if none.
  - `stock`: Integer, only if the seller says how many they HAVE ("I have 20 jars", "15 left").
    A pack size like "10 kg" or "box of 6" is NOT stock. Leave it out if unsure.

Then reply in one or two short sentences with what the script reported (posted, or saved
until there is internet). Do not repeat the whole listing; the card shows it.

## Other requests

- **Stock** ("sold 3 scarves", "only 5 jars left", "eggs are sold out"): call `run_js` with
  `{"action": "stock", "listing": "<a word from the product title, e.g. scarf>", ...}` plus ONE of
  `"sold": <number sold>`, `"remaining": <number left>`, or `"sold_out": true`.
  The script updates the count and changes the Telegram post (e.g. to "❌ SOLD OUT").
- **Market price** ("what should I charge?", or right after creating a listing that has NO price):
  call `run_js` with `{"action": "market", "query": "<2-4 product words, e.g. hand knitted wool scarf>",
  "country": "<2-letter country code from the seller's currency or location, default us>"}`.
  Then tell the seller the price range in one sentence and say these are online-shop prices,
  only a rough guide for a farm or market stall. Never change the listing's price yourself.
- "Post my listings" / "I have internet now": call `run_js` with `{"action": "publish"}`.
- "Show my listings" / "what do I have left?": call `run_js` with `{"action": "list"}`.

## Example

Photo: a striped wool scarf. Note: "hand-knitted scarf, wool, $25".
Data: `{"action": "create", "title": "Warm Hand-Knitted Striped Wool Scarf", "body": "A soft wool scarf, knitted by hand in bright stripes. It keeps you warm on cold mornings and makes a lovely gift. Send me a message to reserve yours.", "tags": ["hand-knitted", "wool scarf", "handmade gift"], "note": "hand-knitted scarf, wool, $25"}`
