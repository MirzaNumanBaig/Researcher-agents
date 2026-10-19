"""Render data/leads.json into docs/index.html, grouped by celebrity."""
import html
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
cfg = json.loads((ROOT / "config.json").read_text())
leads = json.loads((ROOT / "data" / "leads.json").read_text())


def item(l):
    return (f'<li><a href="{html.escape(l["url"])}">{html.escape(l["title"])}</a>'
            f'<small>{html.escape(l["source"])} · {html.escape((l["published"] or "")[:16])}</small>'
            f'<p>{html.escape(l["summary"])}</p></li>')


sections = []
for name in cfg["celebrities"]:
    mine = [l for l in leads if name in l.get("celebrities", [])]
    body = "\n".join(item(l) for l in mine) or "<li><small>No recent stories.</small></li>"
    sections.append(f"<h2>{html.escape(name)} <small>({len(mine)})</small></h2><ul>{body}</ul>")

page = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(cfg["country"])} Celebrity News Leads</title>
<style>body{{font:16px system-ui;max-width:760px;margin:0 auto;padding:16px}}
ul{{padding:0}}li{{list-style:none;margin:0 0 18px}}small{{display:block;color:#666;font-weight:400}}
h2 small{{display:inline}}p{{margin:4px 0}}
@media(prefers-color-scheme:dark){{body{{background:#111;color:#eee}}a{{color:#8ab4ff}}small{{color:#999}}}}</style>
<h1>{html.escape(cfg["country"])} Celebrity News Leads</h1>
<p>{len(leads)} leads · updated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC</p>
{"".join(sections)}</html>"""
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs" / "index.html").write_text(page)
print("dashboard built")
