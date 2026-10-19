"""Decide whether this workflow run should collect. Prints run=yes|no for GITHUB_OUTPUT.
The workflow wakes every hour; a scheduled wake collects only when interval_hours have passed since the last run."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
cfg = json.loads((ROOT / "config.json").read_text())
event = os.environ.get("GITHUB_EVENT_NAME", "")
usage_file = ROOT / "data" / "usage.json"
last = json.loads(usage_file.read_text()).get("last_run") if usage_file.exists() else None
due = True
if last:
    hours = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() / 3600
    due = hours >= cfg.get("interval_hours", 3) - 0.2  # tolerate cron start jitter
if event == "workflow_dispatch":
    run = True  # "Run now" always runs
elif cfg.get("paused"):
    run = False
elif event == "schedule":
    run = due
else:
    run = True  # config change: refresh straight away
print("run=" + ("yes" if run else "no"))
