"""Numbers for the dashboard's Usage view (standard library only): Cloudflare neuron estimates per account and Claude token counts for article writing."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FREE_NEURONS = 10000


def _json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def neuron_summary(root=ROOT, cfg=None, today=None):
    """Today's estimated neurons per account slot against the budget, the picture attempts, and the last 14 days.
    Read from articles/image-meta/_usage.json, which agents/cf_accounts.py keeps. The numbers are ESTIMATES made from the calls we sent;
    an account Cloudflare itself stopped ("daily free allocation used up") counts as the full free limit and is flagged `spent`."""
    cfg = cfg or {}
    pipe = cfg.get("image_pipeline") or {}
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    u = _json(Path(root) / "articles" / "image-meta" / "_usage.json", {})
    u = u if isinstance(u, dict) else {}
    is_today = u.get("date") == today
    todays = (u.get("neurons") or {}) if is_today else {}
    days = dict(u.get("history") or {})
    if u.get("date") and not is_today:
        days[u["date"]] = {"neurons": u.get("neurons") or {}, "images": u.get("images", 0)}
    if is_today:
        days[today] = {"neurons": todays, "images": u.get("images", 0)}
    history = [{"date": d, "total": sum(int(x) for x in (v.get("neurons") or {}).values()), "images": v.get("images", 0)}
               for d, v in sorted(days.items())[-14:]]
    spent = {int(k) for k in (u.get("spent") or []) if str(k).isdigit()} if is_today else set()
    slots = sorted({int(k) for k in todays if str(k).isdigit()} | spent | {1})
    return {"date": today, "has_data": bool(u), "budget": int(pipe.get("neuron_budget", 9000)), "free_limit": FREE_NEURONS,
            "model": pipe.get("image_model") or "@cf/black-forest-labs/flux-2-klein-4b", "images_today": u.get("images", 0) if is_today else 0,
            "accounts": [{"slot": s, "used": max(int(todays.get(str(s), 0)), FREE_NEURONS if s in spent else 0), "spent": s in spent} for s in slots], "history": history}


def claude_summary(root=ROOT, today=None):
    """Token counts for article writing: today, 7 days, 30 days, per day, per writer account and the latest writer runs. Cost is API-equivalent, not billed on a plan."""
    recs = [r for r in (_json(Path(root) / "data" / "claude_usage.json", {}).get("records") or []) if isinstance(r, dict)]
    now = datetime.strptime(today, "%Y-%m-%d") if today else datetime.now(timezone.utc).replace(tzinfo=None)
    day = lambda n: (now - timedelta(days=n)).strftime("%Y-%m-%d")  # noqa: E731
    keys = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "turns", "cost_usd")

    def total(rows):
        t = {k: sum((r.get(k) or 0) for r in rows) for k in keys}
        t["runs"] = len(rows)
        t["articles"] = len({(r.get("batch"), r.get("celebrity")) for r in rows})
        t["tokens"] = t["input_tokens"] + t["output_tokens"]
        t["cost_usd"] = round(t["cost_usd"], 2)
        return t

    by_day = {}
    for r in recs:
        by_day.setdefault(r.get("date", ""), []).append(r)
    writers = {}
    for r in recs:
        if r.get("date", "") >= day(29):
            writers.setdefault(r.get("writer", "?"), []).append(r)
    return {"has_data": bool(recs), "today": total([r for r in recs if r.get("date") == day(0)]),
            "week": total([r for r in recs if r.get("date", "") >= day(6)]), "month": total([r for r in recs if r.get("date", "") >= day(29)]),
            "days": [{"date": d, **total(by_day.get(d, []))} for d in [day(n) for n in range(13, -1, -1)]],
            "writers": {w: total(rows) for w, rows in sorted(writers.items())},
            "recent": [{k: r.get(k) for k in ("time", "celebrity", "article", "writer", "ok", "input_tokens", "output_tokens", "cache_read_tokens", "turns", "seconds", "cost_usd")}
                       for r in reversed(recs[-12:])]}
