"""Record the Claude token usage of one article's writer run (standard library only).

  python agents/record_usage.py --celebrity "Name" --batch "2026-10-28 09:00" --article articles/x.md  claude1=/path/execution.json claude2=...

Each NAME=PATH is the `execution_file` output of anthropics/claude-code-action for that writer step (an empty or missing path means that writer did not run).
The file is the run's message log; its final `result` message carries the token counts, turns and cost. One record per writer run is appended to
data/claude_usage.json, which the dashboard's Usage view reads. Tokens are exact; cost_usd is the API-equivalent price, NOT what a Claude plan is billed.
A problem here must never fail the article job, so every error ends quietly (exit 0)."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "data" / "claude_usage.json"
KEEP = 1500
KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def _messages(text):
    """The run's messages from a JSON array, a single object or JSON lines."""
    text = (text or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else [data]
    except ValueError:
        out = []
        for line in text.splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out


def _num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def parse_execution(text):
    """{ok, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, turns, seconds, cost_usd} or None when there is no usage in it."""
    msgs = [m for m in _messages(text) if isinstance(m, dict)]
    result = next((m for m in reversed(msgs) if m.get("type") == "result"), None)
    if result and isinstance(result.get("usage"), dict):
        u, ok, turns, ms, cost = result["usage"], result.get("subtype") == "success" and not result.get("is_error"), _num(result.get("num_turns")), result.get("duration_ms"), result.get("total_cost_usd")
    else:  # no final result message (the run was cut off): add up the assistant messages, the last usage of each message id
        per = {}
        for i, m in enumerate(msgs):
            msg = m.get("message") if m.get("type") == "assistant" else None
            if isinstance(msg, dict) and isinstance(msg.get("usage"), dict):
                per[msg.get("id") or f"#{i}"] = msg["usage"]
        if not per:
            return None
        u = {k: sum(_num(x.get(k)) for x in per.values()) for k in KEYS}
        ok, turns, ms, cost = False, len(per), None, None
    return {"ok": bool(ok), "input_tokens": _num(u.get("input_tokens")), "output_tokens": _num(u.get("output_tokens")),
            "cache_read_tokens": _num(u.get("cache_read_input_tokens")), "cache_write_tokens": _num(u.get("cache_creation_input_tokens")),
            "turns": turns, "seconds": round((ms or 0) / 1000), "cost_usd": round(float(cost), 4) if isinstance(cost, (int, float)) else None}


def load(path=None):
    try:
        data = json.loads((path or FILE).read_text())
        return data if isinstance(data, dict) and isinstance(data.get("records"), list) else {"records": []}
    except (OSError, ValueError):
        return {"records": []}


def append(records, path=None):
    path = path or FILE
    data = load(path)
    data["records"] = (data["records"] + records)[-KEEP:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1) + "\n")


def main(argv):
    args, runs, i = {}, [], 0
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv):
            args[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            runs.append(argv[i])
            i += 1
    now = datetime.now(timezone.utc)
    records = []
    for run in runs:
        writer, _, path = run.partition("=")
        if not path.strip():
            continue
        try:
            usage = parse_execution(Path(path.strip()).read_text())
        except OSError:
            usage = None
        if usage:
            records.append({"date": now.strftime("%Y-%m-%d"), "time": now.isoformat(timespec="seconds"), "batch": args.get("batch", ""),
                            "celebrity": args.get("celebrity", ""), "article": Path(args.get("article", "")).name, "writer": writer, **usage})
    if records:
        append(records)
    print(f"recorded {len(records)} writer run(s)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:  # never fail the article job over a usage record
        print(f"usage not recorded: {e}", file=sys.stderr)
        sys.exit(0)
