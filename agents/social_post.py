"""Share newly published posts on social media through Zernio (https://zernio.com), right away (no schedule).

Runs after every WordPress send (publish-wordpress.yml). Needs the GitHub secret ZERNIO_API_KEY; without it nothing happens.
Settings in config.json "social": {"enabled": false, "platforms": ["pinterest"] (or facebook), "pinterest_board": "" (a board id; empty = the account's first board), "daily_cap": 10, "min_gap_minutes": 10, "per_run": 1, "since": "YYYY-MM-DD"}.
A post is shared when: it is live on the site with its featured image, it is newer than `since` (set when the switch is turned on, so nothing old is
shared), nobody blocked is in it, it was not shared before (data/social.json), and the daily cap and the gap since the last share allow it. Newest first.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "social.json"
API = "https://zernio.com/api/v1"
DEFAULTS = {"enabled": False, "platforms": ["pinterest", "threads"], "pinterest_board": "", "daily_cap": 10, "min_gap_minutes": 10, "per_run": 1, "since": ""}


def split(text):
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    return (m.group(1), m.group(2)) if m else ("", text)


def field(front, key):
    m = re.search(rf"^{key}:\s*(.*)$", front, re.M)
    v = m.group(1).strip() if m else ""
    if v[:1] in "\"'" and v[-1:] == v[:1] and len(v) > 1:
        try:
            return json.loads(v) if v[0] == '"' else v[1:-1]
        except ValueError:
            return v[1:-1]
    return v


def load_state():
    try:
        s = json.loads(STATE.read_text())
    except (OSError, ValueError):
        s = {}
    s.setdefault("shared", {})
    s.setdefault("log", [])  # ISO times of shares, newest last
    return s


def settings(cfg):
    return {**DEFAULTS, **(cfg.get("social") or {})}


def candidates(cfg, state, articles_dir=None):
    """[(batch label, wp_id, file stem, title, description, link, celebrity, media id, image url)] of posts that may be shared, newest first."""
    since = settings(cfg)["since"]
    blocked = {b.lower() for b in cfg.get("blocked", [])}
    out = []
    for f in sorted((articles_dir or ROOT / "articles").glob("*.md"), reverse=True):
        front, _ = split(f.read_text())
        wp_id, celeb = field(front, "wp_id"), field(front, "celebrity")
        batch = field(front, "batch")  # "2026-11-27 09:00"
        if field(front, "status") != "sent" or field(front, "wp_synced") != "publish" or not wp_id or wp_id in state["shared"]:
            continue
        if not field(front, "wp_image") and not field(front, "wp_media_id"):
            continue  # never share a post without its picture
        if not since or batch[:10] < since or celeb.lower() in blocked:
            continue
        link = field(front, "wp_link")
        if not link.startswith("http"):
            continue
        out.append((batch, wp_id, f.stem, field(front, "title"), field(front, "description"), link, celeb, field(front, "wp_media_id"), field(front, "wp_image")))
    return out


def allowed_now(cfg, state, now):
    """How many shares may go out right now (daily cap and the gap since the last one)."""
    s = settings(cfg)
    today = [t for t in state["log"] if t[:10] == now.strftime("%Y-%m-%d")]
    room = s["daily_cap"] - len(today)
    if room <= 0:
        return 0
    if state["log"]:
        last = datetime.fromisoformat(state["log"][-1])
        if (now - last).total_seconds() < s["min_gap_minutes"] * 60:
            return 0
    return min(room, s["per_run"])


def caption(title, description, link):
    d = description.strip()
    return "\n\n".join(x for x in (title.strip(), d if d and d != title else "", f"Read more: {link}") if x)


def call(method, path, key, body=None, headers=None):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "researcher-agents", **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"{}")


def accounts(key, platforms):
    data = call("GET", "/accounts", key)
    return [(a["platform"], a["_id"]) for a in data.get("accounts", []) if a.get("platform") in platforms and a.get("_id")]


def pinterest_board(key, account_id, wanted=""):
    """Board id for pins: the configured one, else the account's first board."""
    boards = call("GET", f"/accounts/{account_id}/pinterest-boards", key).get("boards", [])
    if wanted and any(b.get("id") == wanted for b in boards):
        return wanted
    if wanted:  # a board NAME was given
        for b in boards:
            if (b.get("name") or "").lower() == wanted.lower():
                return b["id"]
    if not boards:
        raise RuntimeError("the Pinterest account has no board; create one in Pinterest")
    return boards[0]["id"]


def image_url(front_wp_media, fallback, site=""):
    """Full-size featured image URL: the public WordPress media record, else the dashboard-sized link kept in the article."""
    if front_wp_media and site:
        try:
            with urllib.request.urlopen(urllib.request.Request(f"{site.rstrip('/')}/wp-json/wp/v2/media/{front_wp_media}?_fields=source_url", headers={"User-Agent": "researcher-agents"}), timeout=30) as r:
                u = json.loads(r.read()).get("source_url", "")
                if u.startswith("http"):
                    return u
        except Exception:
            pass
    return fallback


def entries(key, accts, s, title, text, link, img, desc=""):
    """The `platforms` array of the Zernio post: one entry per connected account, with the text and options each network needs."""
    out = []
    for platform, account_id in accts:
        e = {"platform": platform, "accountId": account_id}
        if platform == "pinterest":
            e["customContent"] = (desc.strip() or title.strip())[:800]
            e["platformSpecificData"] = {"title": title[:100], "boardId": pinterest_board(key, account_id, s.get("pinterest_board", "")), "link": link}
        elif platform == "threads":
            e["customContent"] = threads_text(title, desc, link)
        out.append(e)
    return out


def threads_text(title, desc, link, limit=500):
    """A Threads post (500 characters): the headline, as much of the description as fits, and the link."""
    tail = f"\n\n{link}"
    room = limit - len(title) - len(tail) - 2
    d = desc.strip()
    if d and d != title.strip() and room > 40:
        d = d if len(d) <= room else d[: room - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
        return f"{title.strip()}\n\n{d}{tail}"
    return f"{title.strip()[: limit - len(tail)]}{tail}"


def share(key, accts, s, title, text, link, img, wp_id, desc=""):
    body = {"content": text, "publishNow": True, "platforms": entries(key, accts, s, title, text, link, img, desc)}
    if img:  # Pinterest needs a picture; Threads shows it with the post
        body["mediaItems"] = [{"type": "image", "url": img}]
    return call("POST", "/posts", key, body, {"Idempotency-Key": f"moduscarry-{wp_id}"})


def main(argv=None):
    a = sys.argv[1:] if argv is None else argv
    cfg = json.loads((ROOT / "config.json").read_text())
    s = settings(cfg)
    state = load_state()
    if not s["enabled"]:
        print("social sharing is off (config.json social.enabled).")
        return 0
    key = os.environ.get("ZERNIO_API_KEY", "")
    dry = "--dry" in a
    if not key and not dry:
        print("ZERNIO_API_KEY is not set; nothing shared.")
        state["error"] = "ZERNIO_API_KEY is not set in the GitHub secrets"
        STATE.write_text(json.dumps(state, indent=1, ensure_ascii=False))
        return 0
    now = datetime.now(timezone.utc)
    room = allowed_now(cfg, state, now)
    todo = candidates(cfg, state)
    print(f"{len(todo)} posts could be shared; room now: {room}")
    if not room or not todo:
        return 0
    try:
        accts = [] if dry else accounts(key, s["platforms"])
        if not dry and not accts:
            raise RuntimeError(f"no connected {', '.join(s['platforms'])} account in Zernio")
        if not dry:
            state["missing"] = [p for p in s["platforms"] if p not in {a for a, _ in accts}]  # configured but not connected in Zernio
        site = (cfg.get("site") or {}).get("url", "")
        for batch, wp_id, stem, title, desc, link, celeb, media_id, img0 in todo[:room]:
            text = caption(title, desc, link)
            img = image_url(media_id, img0, site)
            if dry:
                print(f"--- would share {stem}:\n{text}\n")
                continue
            res = share(key, accts, s, title, text, link, img, wp_id, desc)
            post = res.get("post") or {}
            urls = {x.get("platform"): x.get("platformPostUrl", "") for x in post.get("platforms", []) if isinstance(x, dict)}
            state["shared"][wp_id] = {"at": now.isoformat(timespec="seconds"), "post": post.get("_id", ""), "title": title, "link": link,
                                      "platforms": [{"platform": p, "url": urls.get(p, "")} for p, _ in accts]}
            state["log"] = (state["log"] + [now.isoformat(timespec="seconds")])[-200:]
            state.pop("error", None)
            print(f"shared {stem} -> {', '.join(p for p, _ in accts)}")
    except urllib.error.HTTPError as e:
        state["error"] = f"Zernio HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
        print(state["error"], file=sys.stderr)
    except Exception as e:  # never break the publish workflow
        state["error"] = str(e)[:200]
        print(f"social sharing failed: {e}", file=sys.stderr)
    if not dry:
        STATE.write_text(json.dumps(state, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
