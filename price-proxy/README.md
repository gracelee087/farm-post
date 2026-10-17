# price-proxy

Holds the SerpApi key server-side and returns a CORS-enabled price summary (Python 3.11, standard library only).

1. Render Dashboard > New > Blueprint, pick this repo, set the Blueprint file path to `price-proxy/render.yaml`.
2. When prompted, paste your SerpApi key into `SERPAPI_API_KEY` (it is `sync: false`, so it is never in git).
3. After deploy, `GET /health` should return `ok`. Limits: 1 h cache per query, 200 SerpApi calls per UTC day (then 429).
4. Example: `curl "https://<your-service>.onrender.com/price?q=organic+honey+500g&gl=us"`
   returns `{"query","gl","count","min","median","max","currency_hint","examples":[{"title","price","source"}]}`.

Local: `SERPAPI_API_KEY=... PORT=8000 python server.py`. Tests (offline): `python -m unittest discover -s price-proxy`.
