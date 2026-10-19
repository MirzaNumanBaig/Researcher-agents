"""Decide whether this workflow run should collect. Prints run=yes|no for GITHUB_OUTPUT."""
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

cfg = json.loads((Path(__file__).resolve().parent.parent / "config.json").read_text())
event = os.environ.get("GITHUB_EVENT_NAME", "")
hour = datetime.now(ZoneInfo(cfg.get("timezone", "UTC"))).hour
if event == "workflow_dispatch":
    run = True  # "Run now" always runs
elif cfg.get("paused"):
    run = False
elif event == "schedule":
    run = hour in cfg.get("run_hours", [hour])
else:
    run = True  # config change: refresh straight away
print("run=" + ("yes" if run else "no"))
