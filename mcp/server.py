"""Researcher-agents MCP server (stdio, standard library only).

Lets any Claude account read the news data and control the GitHub-hosted system. All state lives in the
GitHub repo; this server only calls the GitHub REST API, so nothing else needs hosting.

Env: GITHUB_TOKEN (fine-grained, this repo only: Contents + Actions read/write), GITHUB_REPO (optional).
"""
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

REPO = os.environ.get("GITHUB_REPO", "MirzaNumanBaig/Researcher-agents")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
API = f"https://api.github.com/repos/{REPO}"


def gh(path, method="GET", body=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "researcher-agents-mcp"}
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    req = urllib.request.Request(API + path, method=method, headers=headers,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GitHub {e.code}: {e.read().decode()[:200]}")


def read_file(path):
    f = gh(f"/contents/{path}")
    return base64.b64decode(f["content"]).decode(), f["sha"]


def write_file(path, text, message, sha=None):
    body = {"message": message, "content": base64.b64encode(text.encode()).decode()}
    if sha:
        body["sha"] = sha
    gh(f"/contents/{path}", "PUT", body)


def edit_config(fn, message):
    text, sha = read_file("config.json")
    cfg = json.loads(text)
    fn(cfg)
    write_file("config.json", json.dumps(cfg, indent=2) + "\n", message, sha)
    return cfg


def stories():
    return json.loads(read_file("data/stories.json")[0])


def slugify(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:60]


# ---- tools -----------------------------------------------------------------
def get_status():
    cfg = json.loads(read_file("config.json")[0])
    usage = json.loads(read_file("data/usage.json")[0])
    runs = gh("/actions/runs?per_page=5")["workflow_runs"]
    return {"country": cfg["country"], "celebrities": cfg["celebrities"], "paused": cfg.get("paused", False),
            "interval_hours": cfg.get("interval_hours", 3), "last_run_utc": usage.get("last_run"),
            "runs_this_month": usage.get(datetime.now(timezone.utc).strftime("%Y-%m"), 0),
            "recent_workflow_runs": [f'{r["created_at"]} {r["name"]} {r["conclusion"] or r["status"]}' for r in runs]}


def list_batches():
    out = {}
    for s in stories():
        out[s["batch"]] = out.get(s["batch"], 0) + 1
    return dict(sorted(out.items(), reverse=True))


def get_stories(batch="", celebrity="", limit=30):
    res = [s for s in stories() if (not batch or s["batch"] == batch)
           and (not celebrity or celebrity in s["celebrities"])]
    return res[:limit]


def run_now():
    gh("/actions/workflows/collect.yml/dispatches", "POST", {"ref": "main"})
    return "Collection run started."


def set_paused(paused):
    edit_config(lambda c: c.update(paused=bool(paused)), "MCP: set paused")
    return f"paused = {bool(paused)}"


def set_interval(hours):
    if not 1 <= int(hours) <= 24:
        raise ValueError("hours must be 1-24")
    edit_config(lambda c: c.update(interval_hours=int(hours)), "MCP: set interval")
    return f"interval_hours = {int(hours)}"


def add_celebrity(name):
    cfg = edit_config(lambda c: (c["celebrities"].append(name) if name not in c["celebrities"] else None,
                                 c.setdefault("profiles", {}).setdefault(name, {})), f"MCP: add {name}")
    return cfg["celebrities"]


def remove_celebrity(name):
    cfg = edit_config(lambda c: c.update(celebrities=[n for n in c["celebrities"] if n != name]), f"MCP: remove {name}")
    return cfg["celebrities"]


def save_draft(title, body_markdown, sources, batch=""):
    """Save an article draft to articles/ with status 'pending' (awaiting approval)."""
    slug = slugify(title)
    path = f"articles/{(batch or datetime.now(timezone.utc).strftime('%Y-%m-%d-%H%M')).replace(' ', '-').replace(':', '')}-{slug}.md"
    front = "---\n" + f"title: {json.dumps(title)}\nstatus: pending\nbatch: {json.dumps(batch)}\n" \
        + "sources:\n" + "".join(f"  - {json.dumps(s)}\n" for s in sources) + "---\n\n"
    write_file(path, front + body_markdown + "\n", f"MCP: draft {slug}")
    return path


def list_drafts():
    items = gh("/contents/articles")
    out = []
    for it in items:
        if it["name"].endswith(".md"):
            text = read_file(it["path"])[0]
            m = re.search(r"^status: (\w+)", text, re.M)
            t = re.search(r'^title: (.*)$', text, re.M)
            out.append({"path": it["path"], "status": m.group(1) if m else "?", "title": t.group(1) if t else ""})
    return out


def set_draft_status(path, status):
    if status not in ("pending", "approved", "rejected"):
        raise ValueError("status must be pending, approved or rejected")
    text, sha = read_file(path)
    write_file(path, re.sub(r"^status: \w+", f"status: {status}", text, count=1, flags=re.M), f"MCP: {status} {path}", sha)
    return f"{path} -> {status}"


def read_draft(path):
    return read_file(path)[0]


S = lambda **p: {"type": "object", "properties": p, "additionalProperties": False}  # noqa: E731
STR, INT, BOOL = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}
TOOLS = {
    "get_status": (get_status, "Schedule, pause state, celebrities, last run and recent GitHub Actions runs.", S()),
    "list_batches": (list_batches, "Run batches (one per collection run) with story counts.", S()),
    "get_stories": (get_stories, "Grouped news stories (each lists all outlets and links). Filter by batch label and/or celebrity.",
                    S(batch=STR, celebrity=STR, limit=INT)),
    "run_now": (run_now, "Start a collection run immediately.", S()),
    "set_paused": (set_paused, "Pause or resume the scheduled runs.", S(paused=BOOL)),
    "set_interval": (set_interval, "Set hours between runs (1-24).", S(hours=INT)),
    "add_celebrity": (add_celebrity, "Start tracking a celebrity.", S(name=STR)),
    "remove_celebrity": (remove_celebrity, "Stop tracking a celebrity.", S(name=STR)),
    "save_draft": (save_draft, "Save an original article draft (markdown) with its source URLs; status starts as pending approval.",
                   {"type": "object", "properties": {"title": STR, "body_markdown": STR, "sources": {"type": "array", "items": STR}, "batch": STR},
                    "required": ["title", "body_markdown", "sources"]}),
    "list_drafts": (list_drafts, "List article drafts and their approval status.", S()),
    "read_draft": (read_draft, "Read one draft file.", S(path=STR)),
    "set_draft_status": (set_draft_status, "Approve or reject a draft (pending/approved/rejected).", S(path=STR, status=STR)),
}


def handle(msg):
    method, mid = msg.get("method"), msg.get("id")
    if method == "initialize":
        return {"protocolVersion": msg["params"].get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {}},
                "serverInfo": {"name": "researcher-agents", "version": "1.0"}}
    if method == "tools/list":
        return {"tools": [{"name": n, "description": d, "inputSchema": sc} for n, (_, d, sc) in TOOLS.items()]}
    if method == "tools/call":
        name, args = msg["params"]["name"], msg["params"].get("arguments", {})
        try:
            res = TOOLS[name][0](**args)
            text = res if isinstance(res, str) else json.dumps(res, indent=2, ensure_ascii=False)
            return {"content": [{"type": "text", "text": text}]}
        except Exception as e:  # report tool errors to the model instead of crashing
            return {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}
    if method == "ping":
        return {}
    return None if mid is None else {"__error": (-32601, "Method not found")}


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        msg = json.loads(line)
        res = handle(msg)
        if msg.get("id") is None:
            continue
        out = {"jsonrpc": "2.0", "id": msg["id"]}
        if isinstance(res, dict) and "__error" in res:
            out["error"] = {"code": res["__error"][0], "message": res["__error"][1]}
        else:
            out["result"] = res
        print(json.dumps(out), flush=True)


if __name__ == "__main__":
    main()
