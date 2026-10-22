"""Save the website's categories, tags and recent posts to data/wp_site.json so articles can use real
categories/tags and link to existing posts. Uses the public WordPress REST API (WP_URL env)."""
import html
import json
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = os.environ.get("WP_URL", "").rstrip("/")


def get(path):
    req = urllib.request.Request(f"{URL}/wp-json/wp/v2/{path}", headers={"User-Agent": "researcher-agents"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main():
    if not URL:
        print("WP_URL not set; skipping.")
        return
    site = {
        "categories": [{"id": c["id"], "name": html.unescape(c["name"]), "count": c["count"], "link": c.get("link", "")} for c in get("categories?per_page=100")],
        "tags": [{"id": t["id"], "name": html.unescape(t["name"]), "count": t["count"], "link": t.get("link", "")} for t in get("tags?per_page=100&orderby=count&order=desc")],
        # only published posts come back from the public API, so every link here is live
        "recent_posts": [{"title": html.unescape(p["title"]["rendered"]), "link": p["link"], "categories": p["categories"], "tags": p.get("tags", [])}
                         for p in get("posts?per_page=100&_fields=title,link,categories,tags")],
    }
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "wp_site.json").write_text(json.dumps(site, indent=2, ensure_ascii=False))
    print(f"{len(site['categories'])} categories, {len(site['tags'])} tags, {len(site['recent_posts'])} posts")


if __name__ == "__main__":
    main()
