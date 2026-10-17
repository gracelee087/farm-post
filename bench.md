# Benchmark: gemma4:e4b vs gemma3:4b

Measured 2026-10-17 on the dev laptop: Windows 11, CPU only (AMD integrated graphics, no dedicated GPU), 15.4 GB RAM, Ollama 0.32.15.
Call: `generate_post()` from `generate.py` (`/api/chat`, `format: "json"`, `stream: false`, `think: false`). Photos are the 1280px thumbnails in `samples/`.
Before each model's first run, both models were unloaded (`keep_alive: 0`), so the **cold** run includes model load time.
Each row is one single run. No repeats, so expect run-to-run variance.

## Notes used

| Image | Note |
|---|---|
| potatoes.jpg | `10 kg bag 12 Euro, pickup Saturday` |
| eggs.jpg | `fresh eggs from our hens, 10 pieces 3,50 €` |
| apples.jpg | `apples from our orchard, 5 kg for 7.50 €, self-service stand open daily` |

## Results (wall time in seconds)

| Model | Run | Image | Seconds | Title | Item (model output) | Item correct? | price / unit price (computed in code) |
|---|---|---|---|---|---|---|---|
| gemma4:e4b | **cold (incl. load)** | potatoes | **51.89** | Hearty Farm Potatoes from Our Family Shop | Fresh farm-fresh potatoes | yes | €12.00 / €1.20/kg |
| gemma4:e4b | warm | potatoes | 13.95 | Fresh Family Farm Potatoes - Straight from Our Fields | Fresh harvested round potatoes | yes | €12.00 / €1.20/kg |
| gemma4:e4b | warm | eggs | 28.87 | Fresh Farm Eggs from Our Hens | Fresh farm eggs | yes | €3.50 / €0.35/piece |
| gemma4:e4b | warm | apples | 28.33 | Delicious Farm Fresh Apples from Our Orchard | Fresh orchard apples | yes | €7.50 / €1.50/kg |
| gemma3:4b | **cold (incl. load)** | potatoes | **49.64** | Farm-Fresh Potatoes - A Great Deal! | Fresh Potatoes | yes | €12.00 / €1.20/kg |
| gemma3:4b | warm | potatoes | 13.91 | Local Potatoes - Straight from the Farm | Fresh Potatoes | yes | €12.00 / €1.20/kg |
| gemma3:4b | warm | eggs | 40.82 | Farm Fresh Eggs - Simple & Delicious | Fresh Chicken Eggs | yes | €3.50 / €0.35/piece |
| gemma3:4b | warm | apples | 45.13 | Farm Fresh Apples - A Sweet Treat! | Fresh, Red & Yellow Apples | yes | €7.50 / €1.50/kg |

Warm sum over the 3 images: gemma4:e4b 71.15 s, gemma3:4b 99.86 s.
Errors: none. All 8 runs returned valid JSON with every key.

## Content observations (claims not supported by the photo or note)

- gemma4:e4b: says "freshly harvested" (potatoes, warm run). Nothing else stood out.
- gemma3:4b: "happy hens" (eggs), tags "German produce" / "German eggs" / "Germany", "a taste of rural Germany", and "Grab a 5kg bag" (the note says 5 kg, not a bag). It also repeats prices in the body in mixed formats ("12 Euro", "12€", "7.50€").
- gemma4:e4b did not repeat prices in the body. The UI shows them separately from `price_text` / `unit_price_text`.

## Recommendation

Default to **gemma4:e4b**. In this single set of runs it was faster on warm runs (71 s vs 100 s for 3 images), identified all 3 items, and added fewer unsupported claims. The cold-start times were similar (about 50 s each).
