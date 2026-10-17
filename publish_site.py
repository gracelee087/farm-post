"""Publisher: renders published posts into a static page SITE_DIR/index.html.
No network access - the page is only written to disk."""
import html
import shutil
from pathlib import Path

import outbox

SITE_DIR = Path(__file__).parent / "site"

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Our Shop</title>
<style>
body {{ font-family: sans-serif; font-size: 1.3rem; line-height: 1.5; margin: 0;
       padding: 16px; background: #faf7f0; color: #222; }}
main {{ max-width: 720px; margin: 0 auto; }}
h1 {{ font-size: 2.2rem; }}
article {{ background: #fff; border-radius: 12px; padding: 16px; margin-bottom: 24px;
          box-shadow: 0 1px 4px rgba(0,0,0,.15); }}
article img {{ width: 100%; border-radius: 8px; }}
h2 {{ font-size: 1.8rem; margin: .5em 0 .3em; }}
.price {{ font-size: 1.6rem; font-weight: bold; color: #2d6a1f; }}
.tags {{ color: #666; }}
</style>
</head>
<body>
<main>
<h1>Grown and Made Here</h1>
{articles}
</main>
</body>
</html>
"""

ARTICLE = """<article>
<img src="{image}" alt="{title}">
<h2>{title}</h2>
<p class="price">{price}</p>
<p>{body}</p>
<p class="tags">{tags}</p>
</article>"""


def _article(record: dict) -> str:
    post = record["post"]
    e = html.escape
    price = " &middot; ".join(e(p) for p in (post.get("price_text"), post.get("unit_price_text")) if p)
    tags = " ".join("#" + e(t.lstrip("#")) for t in post.get("tags", []))
    return ARTICLE.format(
        image=e(record["image"]),
        title=e(post.get("title", "")),
        price=price,
        body=e(post.get("body", "")).replace("\n", "<br>"),
        tags=tags,
    )


def publish(new_records: list) -> None:
    """Rebuild the page from already published posts plus new_records (newest first)."""
    records = outbox.published() + list(new_records)
    records.sort(key=lambda r: r["created_at"], reverse=True)
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    for r in records:
        shutil.copyfile(outbox.OUTBOX_DIR / r["image"], SITE_DIR / r["image"])
    page = PAGE.format(articles="\n".join(_article(r) for r in records))
    (SITE_DIR / "index.html").write_text(page, encoding="utf-8")
