"""Finds an official social post (the celebrity's own, or a studio/streamer's) in the articles a story is based on, so the post can embed it.

The embed shows the ORIGINAL picture on the platform it was published on, with the owner's name and link; nothing is copied or re-hosted.
Only posts from accounts in the celebrity's `profiles` (instagram / x) or `config.json` `embed_accounts` are used.
find(front_sources, celebrity) -> {"kind": "x"|"instagram", "url": ...} or None. Run by publish_wordpress.py when it sends an article.
"""
import json
import re
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_PAGES = 3


def handles(celebrity):
    cfg = json.loads((ROOT / "config.json").read_text())
    prof = (cfg.get("profiles") or {}).get(celebrity) or {}
    names = {urllib.parse.urlparse(prof.get(k) or "").path.strip("/").split("/")[0].lower() for k in ("instagram", "x")}
    names |= {h.lower().lstrip("@") for h in cfg.get("embed_accounts", [])}
    return {n for n in names if n}


def scan(page, ok):
    page = page.replace("\\/", "/")
    for m in re.finditer(r"https?://(?:www\.)?(?:x|twitter)\.com/([A-Za-z0-9_]+)/status/(\d+)", page):
        if m.group(1).lower() in ok:
            return {"kind": "x", "url": f"https://x.com/{m.group(1)}/status/{m.group(2)}"}
    for blk in re.finditer(r"<blockquote[^>]*instagram-media.*?</blockquote>", page, re.S | re.I):
        text = blk.group(0)
        who = {h.lower() for h in re.findall(r"@([A-Za-z0-9_.]+)", text)}
        link = re.search(r"https?://(?:www\.)?instagram\.com/(p|reel)/([A-Za-z0-9_-]+)", text)
        if link and who & ok:
            return {"kind": "instagram", "url": f"https://www.instagram.com/{link.group(1)}/{link.group(2)}/"}
    return None


def find(sources, celebrity):
    import fetch_sources as fs
    ok = handles(celebrity)
    for url in sources[:MAX_PAGES]:
        try:
            hit = scan(fs.get(fs.resolve(url)), ok)
        except Exception:
            continue
        if hit:
            return hit
    return None


def html(embed):
    if embed["kind"] == "x":  # the platform's own embed markup; widgets.js turns it into the live post
        handle = embed["url"].split("/")[3]
        return (f'<blockquote class="twitter-tweet"><a href="{embed["url"].replace("https://x.com", "https://twitter.com")}">View the post by @{handle} on X</a></blockquote>'
                '<script async src="https://platform.twitter.com/widgets.js"></script>')
    u = embed["url"]
    return (f'<blockquote class="instagram-media" data-instgrm-permalink="{u}?utm_source=ig_embed" data-instgrm-version="14" '
            f'style="max-width:540px;width:100%"><a href="{u}">View this post on Instagram</a></blockquote>'
            '<script async src="//www.instagram.com/embed.js"></script>')


def insert(content_html, embed):
    """Put the embed after the first paragraph that follows the quick-summary list (end of the article if there is none)."""
    parts = content_html.split("</ul>", 1)
    if len(parts) == 2 and "</p>" in parts[1]:
        head, rest = parts[1].split("</p>", 1)
        return parts[0] + "</ul>" + head + "</p>\n" + html(embed) + rest
    return content_html + "\n" + html(embed)
