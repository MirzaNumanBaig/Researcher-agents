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
h2 small{{display:inline}}#bar{{border:1px solid #8884;border-radius:8px;padding:12px;margin:12px 0 24px;display:flex;flex-wrap:wrap;gap:12px;justify-content:space-between}}button{{font:inherit;padding:6px 12px;border-radius:6px;border:1px solid #8886;background:#8881;color:inherit;cursor:pointer}}#bar small{{width:100%}}p{{margin:4px 0}}
@media(prefers-color-scheme:dark){{body{{background:#111;color:#eee}}a{{color:#8ab4ff}}small{{color:#999}}}}</style>
<h1>{html.escape(cfg["country"])} Celebrity News Leads</h1>
<p>{len(leads)} leads · updated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC</p>
<div id="bar"><div><b id="state"></b><br><span id="timer"></span></div>
<div><button id="run">Run now</button> <button id="pause"></button> <button id="add">+ Add celebrity</button> <button id="tok" title="GitHub token">🔑</button></div>
<small id="msg"></small></div>
{"".join(sections)}
<script>
const REPO="MirzaNumanBaig/Researcher-agents",PAUSED={str(bool(cfg.get("paused"))).lower()};
const $=i=>document.getElementById(i);let paused=PAUSED;
function nextRun(){{const d=new Date(),n=new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),d.getUTCDate(),(Math.floor(d.getUTCHours()/3)+1)*3));return n}}
function tick(){{$("state").textContent=paused?"⏸ Paused — scheduled runs are off":"▶ Running every 3 hours";
$("pause").textContent=paused?"Continue":"Pause";
if(paused){{$("timer").textContent="Next run: none (paused)";return}}
const ms=nextRun()-new Date(),h=Math.floor(ms/36e5),m=Math.floor(ms%36e5/6e4),s=Math.floor(ms%6e4/1e3);
$("timer").textContent="Next run in "+h+"h "+m+"m "+s+"s (approx., GitHub can start a few minutes late)"}}
setInterval(tick,1000);tick();
const say=t=>$("msg").textContent=t;
function token(force){{let t=localStorage.getItem("gh_token");if(!t||force){{t=prompt("Paste a GitHub fine-grained token for "+REPO+" (Contents + Actions: read & write). It is stored only in this browser.");if(t)localStorage.setItem("gh_token",t.trim())}}return localStorage.getItem("gh_token")}}
async function gh(path,opt={{}}){{const t=token();if(!t)throw Error("No token");const r=await fetch("https://api.github.com/repos/"+REPO+path,{{...opt,headers:{{Authorization:"Bearer "+t,Accept:"application/vnd.github+json"}}}});if(!r.ok)throw Error(r.status+" "+(await r.text()).slice(0,120));return r.status==204?null:r.json()}}
async function editCfg(fn){{const f=await gh("/contents/config.json");const c=JSON.parse(decodeURIComponent(escape(atob(f.content))));fn(c);
await gh("/contents/config.json",{{method:"PUT",body:JSON.stringify({{message:"Update config from dashboard",sha:f.sha,content:btoa(unescape(encodeURIComponent(JSON.stringify(c,null,2)+"\\n")))}})}})}}
$("tok").onclick=()=>token(true);
$("run").onclick=async()=>{{try{{await gh("/actions/workflows/collect.yml/dispatches",{{method:"POST",body:JSON.stringify({{ref:"main"}})}});say("Run started. Refresh in ~1 minute.")}}catch(e){{say("Failed: "+e.message)}}}};
$("pause").onclick=async()=>{{try{{await editCfg(c=>c.paused=!paused);paused=!paused;tick();say(paused?"Paused. Scheduled runs will skip.":"Continued. Collecting now.")}}catch(e){{say("Failed: "+e.message)}}}};
$("add").onclick=async()=>{{const n=(prompt("Celebrity name?")||"").trim();if(!n)return;try{{await editCfg(c=>{{if(!c.celebrities.includes(n))c.celebrities.push(n)}});say(n+" added. A run starts now; refresh in ~1-2 minutes.")}}catch(e){{say("Failed: "+e.message)}}}};
</script></html>"""
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs" / "index.html").write_text(page)
print("dashboard built")
