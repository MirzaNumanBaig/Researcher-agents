"""Step 6: WordPress. Reuses the repo's existing REST helpers (publish_wordpress.py) for auth, media upload and the featured image."""
import html
import re
import sys
import tempfile
from pathlib import Path

from . import concept


def _pw():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # agents/
    import publish_wordpress as pw
    return pw


def alt_text(analysis, names, blueprint=None, standins=()):
    """One factual sentence describing only what is visible. Never names a person; stand-ins are described as 'a woman' / 'a man'."""
    if concept.is_sensitive(analysis):
        text = f"Illustration of {concept.symbolic_scene(analysis)}"
    elif blueprint and blueprint.get("people") and standins:
        who = [s["presentation"] for s in standins]
        phrase = f"a {who[0]}" if len(who) == 1 else (f"a {who[0]} and a {who[1]}" if who[0] != who[1] else f"two {who[0]}s")
        light = blueprint.get("light", {}).get("source") or analysis["time_and_light"]
        text = f"Illustration of {phrase} in {blueprint.get('setting') or analysis['setting']}, lit by {light}"
    else:
        objs = list(analysis.get("key_objects", [])) + ["soft light"]
        text = f"Illustration of {analysis['setting']} with {objs[0]} and {objs[1]}, lit by {analysis['time_and_light']}"
    text, _ = concept.strip_names(text, names)
    text = re.sub(r"\ban anonymous figure\b|\bthe figure\b", "a person", text)
    if len(text) > 125:
        cut = text[:125]
        text = cut.rsplit(",", 1)[0] if "," in cut else cut.rsplit(" ", 1)[0]  # cut at the last comma (whole phrases), else at a word boundary
    return text.rstrip(" ,.;") + "."


def fetch_post(post_id):
    """{id, title, body, category, source_url, featured_media} for a WordPress post."""
    pw = _pw()
    p = pw.wp_get(f"posts/{post_id}?context=edit&_fields=id,title,content,categories,featured_media,link")
    title = (p["title"].get("raw") if isinstance(p["title"], dict) else p["title"]) or ""
    content = (p["content"].get("raw") if isinstance(p["content"], dict) else p["content"]) or ""
    cats = []
    if p.get("categories"):
        cats = [c["name"] for c in pw.wp_get(f"categories?include={','.join(map(str, p['categories']))}&_fields=id,name")]
    return {"id": p["id"], "title": html.unescape(title), "body": re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", content))).strip(),
            "category": ", ".join(cats), "source_url": p.get("link", ""), "featured_media": p.get("featured_media") or 0}


def posts_without_image(limit=50):
    pw = _pw()
    posts = pw.wp_get("posts?per_page=100&status=publish,draft,pending,future,private&orderby=date&_fields=id,featured_media")
    return [p["id"] for p in posts if not p.get("featured_media")][:limit]


def attach(post_id, webp, filename, alt, caption):
    """Upload to the media library (with alt text and caption) and set it as the post's featured image. Returns (media id, url)."""
    pw = _pw()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / filename
        path.write_bytes(webp)
        media_id, url = pw.upload_media(path, alt, caption)
    pw.wp(f"posts/{post_id}", {"featured_media": media_id})
    return media_id, url
