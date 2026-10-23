"""Send approved drafts in articles/ to WordPress through its REST API (standard library only).

Env (GitHub Actions secrets): WP_URL (https://moduscarry.com), WP_USER, WP_APP_PASSWORD.
Front matter per article:  status: pending|approved|rejected|sent   wp_status: draft|pending|publish|private
 - approved + no wp_id  -> create the post with wp_status, then status: sent, wp_id, wp_link, wp_synced.
 - sent + wp_status != wp_synced -> update the existing post's status (e.g. draft -> publish).
Optional front matter: description (excerpt), categories: [..names..], tags: [..names..] (matched to the site's own).
Before sending, ALL sent posts are checked against WordPress in batches of 100 (one request per 100 posts) and synced back: if you published, unpublished or trashed a post in WordPress,
the article's wp_status follows (status: removed when the post is trashed or deleted), so the dashboard shows the truth.
Each run also records the website's real totals per status (publish/draft/pending/private/future/trash) in data/wp_sync.json for the dashboard.
`--auto-approve` (used by the automatic writing workflow when config.json has auto_send: true) turns new `pending` drafts into `approved`
first, stamping them with the CURRENT config.json wp_default_status (draft / pending / publish), so the dashboard choice applies to everything not yet sent; `skipped` and `rejected` drafts are never sent. Default wp_status for auto-written drafts is `pending` (review in WordPress).
"""
import base64
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text())
DEFAULT_STATUS = CONFIG.get("wp_default_status", "pending")
WP_STATUSES = {"draft", "pending", "publish", "private"}
AUTO = "--auto-approve" in sys.argv
URL, USER, PW = (os.environ.get(k, "").rstrip("/") for k in ("WP_URL", "WP_USER", "WP_APP_PASSWORD"))


def split(text):
    m = re.match(r"---\n(.*?)\n---\n\n?(.*)", text, re.S)
    return (m.group(1), m.group(2)) if m else ("", text)


def field(front, key):
    m = re.search(rf"^{key}: ?(.*)$", front, re.M)
    if not m:
        return ""
    v = m.group(1).strip()
    return json.loads(v) if v.startswith('"') else v


def set_field(front, key, value):
    line = f"{key}: {json.dumps(value) if key in ('title', 'wp_link') else value}"
    if re.search(rf"^{key}: ?.*$", front, re.M):
        return re.sub(rf"^{key}: ?.*$", lambda _: line, front, count=1, flags=re.M)
    return front + "\n" + line


def items(front, key):
    """Read an inline list like  key: ["a", "b"]."""
    m = re.search(rf"^{key}: ?(\[.*\])$", front, re.M)
    try:
        return json.loads(m.group(1)) if m else []
    except ValueError:
        return []


def wp_get(path):
    req = urllib.request.Request(f"{URL}/wp-json/wp/v2/{path}", headers={
        "User-Agent": "researcher-agents",
        "Authorization": "Basic " + base64.b64encode(f"{USER}:{PW}".encode()).decode()})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def term_ids(kind, names, create):
    """Map category/tag names to WordPress ids; tags are created if missing, unknown categories are skipped."""
    known = {html.unescape(t["name"]).lower(): t["id"] for t in wp_get(f"{kind}?per_page=100")}
    ids = []
    for n in names[:5 if kind == "tags" else 2]:
        if n.lower() in known:
            ids.append(known[n.lower()])
        elif create:
            ids.append(wp(kind, {"name": n})["id"])
        else:
            print(f"  category {n!r} does not exist on the site; skipped")
    return ids


def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" rel="noopener">\1</a>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    return re.sub(r"(?<!\*)\*(?!\*)(.+?)\*", r"<em>\1</em>", t)


def to_html(md):
    out, para, items = [], [], []

    def flush():
        nonlocal para, items
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
        if items:
            out.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>")
        para, items = [], []

    for line in md.splitlines():
        h = re.match(r"(#{1,4})\s+(.*)", line)
        if h:
            flush()
            lvl = max(2, len(h.group(1)))  # WordPress supplies the h1 (post title)
            out.append(f"<h{lvl}>{inline(h.group(2))}</h{lvl}>")
        elif re.match(r"\s*[-*]\s+", line):
            if para:
                flush()
            items.append(re.sub(r"^\s*[-*]\s+", "", line))
        elif not line.strip():
            flush()
        else:
            if items:
                flush()
            para.append(line.strip())
    flush()
    return "\n".join(out)


def wp(path, payload):
    req = urllib.request.Request(
        f"{URL}/wp-json/wp/v2/{path}", data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "researcher-agents",
                 "Authorization": "Basic " + base64.b64encode(f"{USER}:{PW}".encode()).decode()})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def upload_media(image_path, alt, caption):
    """Upload an image to the WordPress media library and return its id (needs upload rights for WP_USER)."""
    data = image_path.read_bytes()
    ctype = {".png": "image/png", ".webp": "image/webp"}.get(image_path.suffix.lower(), "image/jpeg")
    req = urllib.request.Request(
        f"{URL}/wp-json/wp/v2/media", data=data, method="POST",
        headers={"Content-Type": ctype, "Content-Disposition": f'attachment; filename="{image_path.name}"', "User-Agent": "researcher-agents",
                 "Authorization": "Basic " + base64.b64encode(f"{USER}:{PW}".encode()).decode()})
    with urllib.request.urlopen(req, timeout=120) as r:
        media = json.loads(r.read())
    wp(f"media/{media['id']}", {"alt_text": alt, "caption": caption, "title": alt})
    return media["id"]


def featured_image(front):
    """(path, alt) of the article's generated image when the file exists and is not yet in WordPress, else None."""
    rel = field(front, "image")
    p = ROOT / "articles" / rel if rel else None
    if p and p.exists() and not field(front, "wp_media_id"):
        return p, field(front, "image_alt") or field(front, "title")
    return None


def live_posts(articles):
    """{wp_id: {status, link}} for every sent article, fetched 100 ids per request. Ids WordPress no longer returns are deleted posts.
    Returns None when the lookup failed, so a network or permission problem is never mistaken for 'everything was deleted'."""
    ids = []
    for f in articles:
        front = split(f.read_text())[0]
        if field(front, "status") == "sent" and field(front, "wp_id").isdigit():
            ids.append(int(field(front, "wp_id")))
    ids = sorted(set(ids))
    found = {}
    try:
        for i in range(0, len(ids), 100):
            chunk = ",".join(map(str, ids[i:i + 100]))
            res = wp_get(f"posts?include={chunk}&per_page=100&orderby=id&status=publish,future,draft,pending,private,trash&context=edit&_fields=id,status,link")
            if not isinstance(res, list):
                return None
            found.update({p["id"]: p for p in res})
    except Exception as e:
        print(f"could not check posts in WordPress: {e}", file=sys.stderr)
        return None
    return found


def sync_from_wp(f, front, body, live):
    """Copy a post's live WordPress status into the article when it was changed in WordPress (not from the dashboard)."""
    want, synced = field(front, "wp_status") or "draft", field(front, "wp_synced")
    if field(front, "status") != "sent" or not field(front, "wp_id") or want != synced or live is None:
        return front  # not sent yet, a dashboard change is waiting to be pushed, or the lookup failed
    post = live.get(int(field(front, "wp_id")), {})
    state = post.get("status", "trash")  # not returned at all = deleted
    if state == synced:
        return front
    if state in WP_STATUSES:
        front = set_field(set_field(front, "wp_status", state), "wp_synced", state)
        if post.get("link"):
            front = set_field(front, "wp_link", post["link"])
        print(f"sync {f.name}: changed in WordPress, now {state}")
    elif state == "trash":  # trashed or deleted
        front = set_field(front, "status", "removed")
        print(f"sync {f.name}: removed in WordPress")
    else:  # e.g. "future" (scheduled in WordPress): leave the article as it is
        return front
    f.write_text(f"---\n{front}\n---\n\n{body}")
    return front


def site_totals():
    """The website's real number of posts per status, from the X-WP-Total header. Written to data/wp_sync.json for the dashboard."""
    totals = {}
    for st in ("publish", "draft", "pending", "private", "future", "trash"):
        req = urllib.request.Request(f"{URL}/wp-json/wp/v2/posts?status={st}&per_page=1&context=edit&_fields=id", headers={
            "User-Agent": "researcher-agents", "Authorization": "Basic " + base64.b64encode(f"{USER}:{PW}".encode()).decode()})
        with urllib.request.urlopen(req, timeout=60) as r:
            totals[st] = int(r.headers["X-WP-Total"])
    totals["checked"] = datetime.now(timezone.utc).isoformat()
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "wp_sync.json").write_text(json.dumps(totals, indent=2) + "\n")
    print("website totals: " + ", ".join(f"{k} {v}" for k, v in totals.items() if k != "checked"))


def main():
    if not (URL and USER and PW):
        print("WP_URL / WP_USER / WP_APP_PASSWORD not set; nothing sent.")
        return
    failed = False
    files = sorted((ROOT / "articles").glob("*.md"))
    live = live_posts(files)
    for f in files:
        front, body = split(f.read_text())
        try:
            front = sync_from_wp(f, front, body, live)
        except Exception as e:  # a sync problem must not block sending new articles
            print(f"  could not check {f.name} in WordPress: {e}", file=sys.stderr)
        status, want = field(front, "status"), field(front, "wp_status") or "draft"
        if AUTO and status == "pending":
            status = "approved"
            front = set_field(front, "status", "approved")
            if DEFAULT_STATUS in WP_STATUSES:  # the dashboard's "New articles arrive as" choice, applied at send time
                want = DEFAULT_STATUS
                front = set_field(front, "wp_status", want)
            f.write_text(f"---\n{front}\n---\n\n{body}")
        if want not in WP_STATUSES:
            print(f"skip {f.name}: bad wp_status {want!r}")
            continue
        try:
            if status == "approved" and not field(front, "wp_id"):
                payload = {"title": field(front, "title"), "content": to_html(body), "status": want}
                if field(front, "description"):
                    payload["excerpt"] = field(front, "description")
                cats, tags = items(front, "categories"), items(front, "tags")
                if cats:
                    payload["categories"] = term_ids("categories", cats, False)
                if tags:
                    payload["tags"] = term_ids("tags", tags, True)
                img = featured_image(front)
                if img:
                    try:
                        media_id = upload_media(img[0], img[1], "Illustration generated with AI")
                        payload["featured_media"] = media_id
                        front = set_field(front, "wp_media_id", media_id)
                    except Exception as e:  # the article still goes out without its picture; it is retried on the next run
                        print(f"  image upload failed for {f.name}: {e}", file=sys.stderr)
                post = wp("posts", payload)
                front = set_field(front, "status", "sent")
            elif status == "sent" and field(front, "wp_id") and featured_image(front):
                img = featured_image(front)  # a sent article that got its image later (or whose upload failed)
                media_id = upload_media(img[0], img[1], "Illustration generated with AI")
                post = wp(f"posts/{field(front, 'wp_id')}", {"featured_media": media_id})
                front = set_field(front, "wp_media_id", media_id)
                if want != field(front, "wp_synced"):
                    post = wp(f"posts/{field(front, 'wp_id')}", {"status": want})
            elif status == "sent" and field(front, "wp_id") and want != field(front, "wp_synced"):
                post = wp(f"posts/{field(front, 'wp_id')}", {"status": want})
            else:
                continue
            front = set_field(set_field(set_field(front, "wp_id", post["id"]), "wp_link", post["link"]), "wp_synced", want)
            f.write_text(f"---\n{front}\n---\n\n{body}")
            print(f"ok {f.name} -> WordPress #{post['id']} ({want})")
        except Exception as e:  # keep going; failed files stay approved and retry on the next run
            failed = True
            print(f"FAIL {f.name}: {e}", file=sys.stderr)
    try:
        site_totals()
    except Exception as e:
        print(f"could not read the website totals: {e}", file=sys.stderr)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
