"""Analytics specialist for social sharing: finds the best hours to post from Zernio's own engagement data.

Reads GET /v1/analytics/best-time per network (average likes + comments + shares + saves per UTC weekday and hour of posts made through Zernio),
keeps the best hours of the day for each network and writes data/social_times.json. agents/social_post.py then shares only in those hours.
Until a network has enough posts (MIN_POSTS) the file says "learning" and sharing is spread over the whole day, so the first posts teach the analyst.
Run weekly (social-analyst.yml) or by hand. Needs ZERNIO_API_KEY.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "social_times.json"
API = "https://zernio.com/api/v1"
MIN_POSTS = 20   # posts per network before its numbers are trusted
KEEP_HOURS = 12  # best hours of the day kept per network (the cap of 20 posts a day still fits)


def fetch(path, key):
    req = urllib.request.Request(API + path, headers={"Authorization": f"Bearer {key}", "User-Agent": "researcher-agents"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def best_hours(slots, keep=KEEP_HOURS):
    """slots = [{day_of_week, hour, avg_engagement, post_count}] -> ([best UTC hours, best first], {weekday: best hour}, posts counted)."""
    by_hour, by_day = {}, {}
    posts = 0
    for s in slots:
        n, avg, h, d = s.get("post_count") or 0, s.get("avg_engagement") or 0, s.get("hour"), s.get("day_of_week")
        if h is None or not n:
            continue
        posts += n
        t = by_hour.setdefault(h, [0.0, 0])
        t[0] += avg * n
        t[1] += n
        if d is not None and (d not in by_day or avg > by_day[d][1]):
            by_day[d] = (h, avg)
    ranked = sorted(by_hour, key=lambda h: -(by_hour[h][0] / by_hour[h][1]))
    return ranked[:keep], {d: v[0] for d, v in by_day.items()}, posts


def analyse(platform_slots):
    """{platform: {status, hours, posts}}: 'ready' once there are enough posts, else 'learning' (no hours, so nothing is restricted)."""
    out = {}
    for platform, slots in platform_slots.items():
        hours, days, posts = best_hours(slots)
        ready = posts >= MIN_POSTS and bool(hours)
        out[platform] = {"status": "ready" if ready else "learning", "posts": posts, "hours": sorted(hours) if ready else [],
                         "best_first": hours[:5] if ready else [], "best_hour_by_weekday": {str(k): v for k, v in days.items()} if ready else {}}
    return out


def main(argv=None):
    cfg = json.loads((ROOT / "config.json").read_text())
    platforms = (cfg.get("social") or {}).get("platforms") or ["pinterest", "threads"]
    key = os.environ.get("ZERNIO_API_KEY", "")
    if not key:
        print("ZERNIO_API_KEY is not set; nothing analysed.")
        return 0
    slots = {}
    for p in platforms:
        try:
            slots[p] = fetch(f"/analytics/best-time?platform={p}&source=late", key).get("slots", [])
        except urllib.error.HTTPError as e:
            print(f"{p}: analytics unavailable (HTTP {e.code})", file=sys.stderr)
            slots[p] = []
    res = analyse(slots)
    OUT.write_text(json.dumps({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "min_posts": MIN_POSTS, "platforms": res}, indent=1))
    for p, r in res.items():
        print(f"{p}: {r['status']} ({r['posts']} posts counted); best UTC hours: {r['best_first'] or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
