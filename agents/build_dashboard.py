"""Render data/leads.json into docs/index.html (single-page dashboard, filtering done in the browser)."""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
cfg = json.loads((ROOT / "config.json").read_text())
leads = json.loads((ROOT / "data" / "leads.json").read_text())

data = {
    "country": cfg["country"],
    "celebrities": cfg["celebrities"],
    "paused": bool(cfg.get("paused")),
    "updated": datetime.now(timezone.utc).isoformat(),
    "leads": [{k: l.get(k) for k in ("title", "url", "source", "published", "summary", "celebrities")} for l in leads],
}

TEMPLATE = r"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Modus Carry · __COUNTRY__ Celebrity News</title>
<style>
:root{--bg:#f6f5f1;--card:#fff;--ink:#17171a;--mut:#6b6b73;--line:#e4e2da;--acc:#b8860b;--accbg:#fbf3dc;--new:#d6336c}
@media(prefers-color-scheme:dark){:root{--bg:#0e0e11;--card:#18181d;--ink:#f1f0ea;--mut:#9a9aa5;--line:#2a2a32;--acc:#e3b341;--accbg:#2a2412;--new:#ff6b9a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
a{color:inherit;text-decoration:none}
header{background:#0e0e11;color:#f1f0ea;padding:20px 16px}
.wrap{max-width:1100px;margin:0 auto;padding:0 16px}header .wrap{padding:0}
.brand{display:flex;align-items:center;gap:12px}
.logo{width:42px;height:42px;border-radius:10px;background:#e3b341;color:#0e0e11;display:grid;place-items:center;font-weight:800;font-size:18px}
h1{font-size:20px;margin:0}.sub{color:#9a9aa5;font-size:13px}
.panel{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:16px 0;display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between}
#state{font-size:15px}#timer{color:var(--mut);font-size:14px}
button,select,input{font:inherit;color:inherit}
button{padding:8px 14px;border-radius:8px;border:1px solid var(--line);background:var(--card);cursor:pointer}
button.pri{background:var(--acc);color:#111;border-color:var(--acc);font-weight:600}
button:hover{filter:brightness(.95)}
#msg{width:100%;color:var(--mut);font-size:13px;min-height:1em}
.tools{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0 10px}
.tools input,.tools select{padding:9px 12px;border-radius:8px;border:1px solid var(--line);background:var(--card)}
.tools input{flex:1;min-width:180px}
.chips{display:flex;gap:8px;overflow-x:auto;padding-bottom:6px;margin-bottom:8px}
.chip{white-space:nowrap;padding:6px 12px;border-radius:99px;border:1px solid var(--line);background:var(--card);cursor:pointer;font-size:14px}
.chip.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
h2{font-size:15px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);margin:26px 0 10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:8px;transition:transform .1s}
.card:hover{transform:translateY(-2px)}
.top{display:flex;gap:10px;align-items:center}
.av{width:30px;height:30px;border-radius:50%;display:grid;place-items:center;color:#fff;font-size:12px;font-weight:700;flex:none}
.who{font-size:13px;font-weight:600}.meta{font-size:12px;color:var(--mut)}
.card h3{font-size:16px;margin:0;line-height:1.35}
.card p{margin:0;color:var(--mut);font-size:14px}
.badge{margin-left:auto;font-size:11px;font-weight:700;background:var(--new);color:#fff;border-radius:99px;padding:2px 8px}
.hero{border-color:var(--acc);background:linear-gradient(var(--accbg),var(--card))}
.empty{color:var(--mut);padding:30px;text-align:center}
footer{color:var(--mut);font-size:12px;padding:30px 0}
</style>
<header><div class="wrap"><div class="brand"><div class="logo">MC</div>
<div><h1>Modus Carry · __COUNTRY__ Celebrity News</h1><div class="sub" id="upd"></div></div></div></div></header>
<main class="wrap">
<div class="panel"><div><div id="state"></div><div id="timer"></div></div>
<div><button class="pri" id="run">Run now</button> <button id="pause"></button> <button id="add">+ Add celebrity</button> <button id="tok" title="GitHub token">🔑</button></div>
<div id="msg"></div></div>
<div class="tools"><input id="q" type="search" placeholder="Search headlines…">
<select id="src"><option value="">All sources</option></select>
<select id="sort"><option value="new">Newest first</option><option value="cel">Group by celebrity</option><option value="src">Group by source</option></select>
<select id="when"><option value="">Any time</option><option value="3">Last 3 hours</option><option value="24">Last 24 hours</option><option value="72">Last 3 days</option></select></div>
<div class="chips" id="chips"></div>
<div id="top"></div><div id="list"></div>
<footer>Headlines come from Google News and Australian entertainment feeds. Google News does not provide images or full summaries; open a story for the full article.</footer>
</main>
<script>
const D=__DATA__,REPO="MirzaNumanBaig/Researcher-agents";
const $=i=>document.getElementById(i),esc=s=>String(s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let paused=D.paused,celeb="";
const COL=["#b8860b","#2b6cb0","#2f855a","#c05621","#6b46c1","#b83280","#2c7a7b"];
const col=n=>COL[[...n].reduce((a,c)=>a+c.charCodeAt(0),0)%COL.length];
const ini=n=>n.split(/\s+/).map(w=>w[0]).slice(0,2).join("").toUpperCase();
const ago=d=>{const m=Math.round((Date.now()-new Date(d))/6e4);if(m<1)return"just now";if(m<60)return m+"m ago";if(m<1440)return Math.round(m/60)+"h ago";return Math.round(m/1440)+"d ago"};
const age=l=>l.published?(Date.now()-new Date(l.published))/36e5:1e9;
$("upd").textContent=D.leads.length+" leads · updated "+ago(D.updated);
[...new Set(D.leads.map(l=>l.source).filter(Boolean))].sort().forEach(s=>$("src").add(new Option(s,s)));
function chips(){const c=[["","All"],...D.celebrities.map(n=>[n,n])];
$("chips").innerHTML=c.map(([v,t])=>'<button class="chip'+(v===celeb?' on':'')+'" data-v="'+esc(v)+'">'+esc(t)+'</button>').join("");
document.querySelectorAll(".chip").forEach(b=>b.onclick=()=>{celeb=b.dataset.v;chips();render()})}
function card(l,hero){const n=(l.celebrities||[])[0]||"";
return '<a class="card'+(hero?' hero':'')+'" href="'+esc(l.url)+'" target="_blank" rel="noopener"><div class="top"><div class="av" style="background:'+col(n)+'">'+esc(ini(n))+'</div><div><div class="who">'+esc((l.celebrities||[]).join(", "))+'</div><div class="meta">'+esc(l.source)+' · '+(l.published?ago(l.published):"")+'</div></div>'+(age(l)<=3?'<span class="badge">NEW</span>':'')+'</div><h3>'+esc(l.title)+'</h3>'+(l.summary?'<p>'+esc(l.summary.slice(0,220))+'</p>':'')+'</a>'}
function render(){
const q=$("q").value.toLowerCase(),s=$("src").value,w=+$("when").value,so=$("sort").value;
let ls=D.leads.filter(l=>(!celeb||(l.celebrities||[]).includes(celeb))&&(!s||l.source===s)&&(!q||(l.title+" "+l.summary+" "+l.source).toLowerCase().includes(q))&&(!w||age(l)<=w));
ls.sort((a,b)=>(b.published||"").localeCompare(a.published||""));
const plain=!q&&!s&&!w&&!celeb&&so==="new";
$("top").innerHTML=plain&&ls.length?'<h2>★ Top stories</h2><div class="grid">'+ls.slice(0,3).map(l=>card(l,1)).join("")+'</div>':"";
if(plain)ls=ls.slice(3);
if(!ls.length&&!plain){$("list").innerHTML='<div class="empty">No stories match.</div>';return}
if(so==="new"){$("list").innerHTML='<h2>Latest ('+ls.length+')</h2><div class="grid">'+ls.map(l=>card(l)).join("")+'</div>';return}
const key=l=>so==="cel"?((l.celebrities||[])[0]||"Other"):(l.source||"Other"),g={};
ls.forEach(l=>(g[key(l)]=g[key(l)]||[]).push(l));
$("list").innerHTML=Object.keys(g).sort().map(k=>'<h2>'+esc(k)+' ('+g[k].length+')</h2><div class="grid">'+g[k].map(l=>card(l)).join("")+'</div>').join("")}
["q","src","sort","when"].forEach(i=>$(i).oninput=render);
function nextRun(){const d=new Date();return new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),d.getUTCDate(),(Math.floor(d.getUTCHours()/3)+1)*3))}
function tick(){$("state").textContent=paused?"⏸ Paused: scheduled runs are off":"▶ Running every 3 hours";$("pause").textContent=paused?"Continue":"Pause";
if(paused){$("timer").textContent="Next run: none (paused)";return}
const ms=nextRun()-new Date(),h=Math.floor(ms/36e5),m=Math.floor(ms%36e5/6e4),s=Math.floor(ms%6e4/1e3);
$("timer").textContent="Next run in "+h+"h "+m+"m "+s+"s (approx.)"}
setInterval(tick,1000);
const say=t=>$("msg").textContent=t;
function token(force){let t=localStorage.getItem("gh_token");if(!t||force){t=prompt("Paste a GitHub fine-grained token for "+REPO+" (Contents + Actions: read & write). Stored only in this browser.");if(t)localStorage.setItem("gh_token",t.trim())}return localStorage.getItem("gh_token")}
async function gh(path,opt={}){const t=token();if(!t)throw Error("No token");const r=await fetch("https://api.github.com/repos/"+REPO+path,{...opt,headers:{Authorization:"Bearer "+t,Accept:"application/vnd.github+json"}});if(!r.ok)throw Error(r.status+" "+(await r.text()).slice(0,120));return r.status==204?null:r.json()}
async function editCfg(fn){const f=await gh("/contents/config.json");const c=JSON.parse(decodeURIComponent(escape(atob(f.content))));fn(c);
await gh("/contents/config.json",{method:"PUT",body:JSON.stringify({message:"Update config from dashboard",sha:f.sha,content:btoa(unescape(encodeURIComponent(JSON.stringify(c,null,2)+"\n")))})})}
$("tok").onclick=()=>token(true);
$("run").onclick=async()=>{try{await gh("/actions/workflows/collect.yml/dispatches",{method:"POST",body:JSON.stringify({ref:"main"})});say("Run started. Refresh in about a minute.")}catch(e){say("Failed: "+e.message)}};
$("pause").onclick=async()=>{try{await editCfg(c=>c.paused=!paused);paused=!paused;tick();say(paused?"Paused. Scheduled runs will skip.":"Continued. Collecting now.")}catch(e){say("Failed: "+e.message)}};
$("add").onclick=async()=>{const n=(prompt("Celebrity name?")||"").trim();if(!n)return;try{await editCfg(c=>{if(!c.celebrities.includes(n))c.celebrities.push(n)});say(n+" added. A run starts now; refresh in 1-2 minutes.")}catch(e){say("Failed: "+e.message)}};
chips();render();tick();
</script></html>"""

page = (TEMPLATE.replace("__COUNTRY__", cfg["country"])
        .replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs" / "index.html").write_text(page)
print("dashboard built")
