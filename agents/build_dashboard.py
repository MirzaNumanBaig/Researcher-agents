"""Render data/leads.json into docs/index.html (single-page dashboard, filtering done in the browser)."""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
cfg = json.loads((ROOT / "config.json").read_text())
leads = json.loads((ROOT / "data" / "leads.json").read_text())

STOP = set("a an the and or of to in on at for with by is are was were as from after before his her their its this that it be has have will new says say over into".split())


NAME_PARTS = {w for n in cfg["celebrities"] for w in n.lower().split()}


def tokens(title):
    return {w for w in re.findall(r"[a-z0-9']+", title.lower()) if w not in STOP and w not in NAME_PARTS and len(w) > 2}


def group(leads):
    """Merge near-duplicate headlines (token overlap) into one story with all outlets."""
    toks = [tokens(l["title"]) for l in leads]
    parent = list(range(len(leads)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(leads)):
        for j in range(i + 1, len(leads)):
            a, b = toks[i], toks[j]
            if a and b and set(leads[i]["celebrities"]) & set(leads[j]["celebrities"]) \
                    and len(a & b) >= 2 and len(a & b) / len(a | b) >= 0.4:
                parent[find(j)] = find(i)
    groups = {}
    for i, l in enumerate(leads):
        groups.setdefault(find(i), []).append(l)
    stories = []
    for ls in groups.values():
        ls.sort(key=lambda l: l.get("published") or "", reverse=True)
        top = ls[0]
        outlets = []
        for l in ls:
            if l["source"] and l["source"] not in [o["source"] for o in outlets]:
                outlets.append({"source": l["source"], "url": l["url"], "article_url": l.get("article_url", ""), "image": l.get("image", "")})
        stories.append({
            "title": top["title"], "url": top["url"], "source": top["source"],
            "published": top["published"], "summary": next((l["summary"] for l in ls if l["summary"]), ""),
            "celebrities": sorted({c for l in ls for c in l["celebrities"]}),
            "outlets": outlets,
            "image": next((l["image"] for l in ls if l.get("image")), ""),
            "image_source": next((l.get("article_url") or l["url"] for l in ls if l.get("image")), ""),
            "batch": min((l.get("batch") or "Earlier" for l in ls), key=lambda b: (b != "Earlier", b)),
        })
    stories.sort(key=lambda x: x["published"] or "", reverse=True)
    return stories


def unquote(v):
    """Front matter values are written as JSON strings ("..." with escapes) or bare words."""
    if v.startswith('"'):
        try:
            return str(json.loads(v))
        except ValueError:
            return v.strip('"')
    return v


def read_articles():
    """Front matter of every article (no body: the dashboard loads a body only when you open its preview)."""
    out = []
    for f in sorted((ROOT / "articles").glob("*.md")):
        text = f.read_text()
        front = text.split("---")[1] if text.startswith("---") else ""
        get = lambda k: unquote((re.search(rf"^{k}: ?(.*)$", front, re.M) or [None, ""])[1].strip())  # noqa: E731
        wp_id = get("wp_id")
        out.append({"path": f"articles/{f.name}", "title": get("title"), "description": get("description"),
                    "status": get("status"), "wp_status": get("wp_status") or "draft", "wp_synced": get("wp_synced"),
                    "batch": get("batch"), "celebrity": get("celebrity"), "wp_link": get("wp_link"),
                    "wp_id": int(wp_id) if wp_id.isdigit() else None, "skip_reason": get("skip_reason"),
                    "rewrite_note": get("rewrite_note")})
    out.sort(key=lambda a: a["batch"] or "", reverse=True)
    return out


def writers():
    """Which writer secrets exist. Only workflows that pass HAS_CLAUDE1.. know; other runs reuse the last answer."""
    f = ROOT / "data" / "writers.json"
    keys = {"claude1": "HAS_CLAUDE1", "claude2": "HAS_CLAUDE2", "claude3": "HAS_CLAUDE3", "codex": "HAS_CODEX"}
    if all(os.environ.get(v) in ("true", "false") for v in keys.values()):
        w = {k: os.environ[v] == "true" for k, v in keys.items()}
        f.write_text(json.dumps(w, indent=2) + "\n")
        return w
    return json.loads(f.read_text()) if f.exists() else None


usage_file = ROOT / "data" / "usage.json"
usage = json.loads(usage_file.read_text()) if usage_file.exists() else {}
stories = group(leads)
data = {
    "country": cfg["country"],
    "repo": os.environ.get("GITHUB_REPOSITORY", "MirzaNumanBaig/Researcher-agents"),
    "site": {"name": (cfg.get("site") or {}).get("name", ""), "url": (cfg.get("site") or {}).get("url", "")},
    "wp_status": cfg.get("wp_default_status", "pending"),
    "auto_send": cfg.get("auto_send", True),
    "ai_images": cfg.get("ai_images", True),
    "timezone": cfg.get("timezone", "UTC"),
    "interval_hours": cfg.get("interval_hours", 3),
    "last_run": usage.get("last_run"),
    "profiles": cfg.get("profiles", {}),
    "runs_this_month": usage.get(datetime.now(timezone.utc).strftime("%Y-%m"), 0),
    "lead_count": len(leads),
    "articles": read_articles(),
    "writers": writers(),
    "celebrities": cfg["celebrities"],
    "paused": bool(cfg.get("paused")),
    "updated": datetime.now(timezone.utc).isoformat(),
    "leads": stories,
    "wp": json.loads((ROOT / "data" / "wp_sync.json").read_text()) if (ROOT / "data" / "wp_sync.json").exists() else None,
}

TEMPLATE = (Path(__file__).parent / "dashboard_template.html").read_text()

site_name = data["site"]["name"].strip()
title = (site_name + " · " if site_name else "") + cfg["country"] + " Celebrity News"
page = (TEMPLATE.replace("__TITLE__", title).replace("__REPO__", data["repo"])
        .replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))
(ROOT / "data" / "stories.json").write_text(json.dumps(stories, indent=2, ensure_ascii=False))  # read by the MCP server
# Read live by the dashboard (GitHub API), so it shows new articles and WordPress status without waiting for Pages.
(ROOT / "data" / "articles.json").write_text(json.dumps(data["articles"], indent=2, ensure_ascii=False) + "\n")
(ROOT / "docs").mkdir(exist_ok=True)
out = ROOT / "docs" / "index.html"
# Skip the write when only the "updated" time changed, so hourly no-op runs do not make a commit.
STAMP = re.compile(r'"updated": "[^"]*"')
if out.exists() and STAMP.sub("", out.read_text()) == STAMP.sub("", page):
    print("dashboard unchanged")
else:
    out.write_text(page)
    print("dashboard built")
