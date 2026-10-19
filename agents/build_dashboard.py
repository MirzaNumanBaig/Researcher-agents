"""Render data/leads.json into docs/index.html (static leads dashboard)."""
import html
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
leads = json.loads((ROOT / "data" / "leads.json").read_text())
rows = "\n".join(
    f'<li><a href="{html.escape(l["url"])}">{html.escape(l["title"])}</a>'
    f'<small>{html.escape(l["source"])} · {html.escape((l["published"] or "")[:16])}</small>'
    f'<p>{html.escape(l["summary"])}</p></li>'
    for l in leads
)
page = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Celebrity News Leads</title>
<style>body{{font:16px system-ui;max-width:760px;margin:0 auto;padding:16px}}
li{{list-style:none;margin:0 0 18px}}small{{display:block;color:#666}}p{{margin:4px 0}}
@media(prefers-color-scheme:dark){{body{{background:#111;color:#eee}}a{{color:#8ab4ff}}small{{color:#999}}}}</style>
<h1>Celebrity News Leads</h1>
<p>{len(leads)} leads · updated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC</p>
<ul style="padding:0">{rows}</ul></html>"""
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs" / "index.html").write_text(page)
print("dashboard built")
