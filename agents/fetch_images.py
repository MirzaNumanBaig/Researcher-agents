"""Attach the news image link to every lead in data/leads.json (stdlib only).

For each lead without an image: resolve the publisher URL (Google News links are redirects), read the start of the page and take its
og:image / twitter:image. Sets  image (URL of the picture), article_url (the publisher page it came from).  Only LINKS are stored, no files.
Leads with no picture are retried on later runs (image_tries, max 3). `--max N` limits pages fetched per run (default 80, newest first).
"""
import json
import re
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from pathlib import Path

import fetch_sources as fs

ROOT = Path(__file__).resolve().parent.parent
LEADS = ROOT / "data" / "leads.json"
MAX_TRIES, HEAD_BYTES = 3, 300_000
META = re.compile(r"<meta\b[^>]*>", re.I)
ATTR = re.compile(r'([\w:-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')
WANTED = ("og:image:secure_url", "og:image:url", "og:image", "twitter:image", "twitter:image:src")


def page_image(page, base):
    """The article's lead picture from its meta tags, as an absolute http(s) URL, or ''."""
    found = {}
    for tag in META.findall(page):
        a = {k.lower(): unescape(v1 or v2) for k, v1, v2 in ATTR.findall(tag)}
        key = (a.get("property") or a.get("name") or "").lower()
        if key in WANTED and a.get("content"):
            found.setdefault(key, a["content"].strip())
    for key in WANTED:
        if key in found:
            url = urllib.parse.urljoin(base, found[key])
            if urllib.parse.urlparse(url).scheme in ("http", "https"):
                return url
    return ""


def fetch_head(url):
    req = fs.urllib.request.Request(url, headers=fs.UA)
    with fs.urllib.request.urlopen(req, timeout=20) as r:
        return r.read(HEAD_BYTES).decode("utf-8", "replace"), r.geturl()


def work(lead):
    try:
        real = fs.resolve(lead["url"])
        page, final = fetch_head(real)
        lead["article_url"] = final
        lead["image"] = page_image(page, final)
    except Exception as e:
        print(f"no image for {lead['url'][:80]}: {e}", file=sys.stderr)
        lead["image"] = ""
    if not lead["image"]:
        lead["image_tries"] = lead.get("image_tries", 0) + 1
    return lead


def main():
    limit = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 80
    leads = json.loads(LEADS.read_text())
    todo = [l for l in leads if not l.get("image") and l.get("image_tries", 0) < MAX_TRIES][:limit]  # leads.json is newest first
    with ThreadPoolExecutor(max_workers=3) as pool:  # few threads: Google rate-limits link resolving
        list(pool.map(work, todo))
    LEADS.write_text(json.dumps(leads, indent=2, ensure_ascii=False))
    have = sum(1 for l in leads if l.get("image"))
    print(f"{sum(1 for l in todo if l.get('image'))} images found in {len(todo)} lookups; {have} of {len(leads)} leads have an image link")


if __name__ == "__main__":
    main()
