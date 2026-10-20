"""Render data/leads.json into docs/index.html (single-page dashboard, filtering done in the browser)."""
import json
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
                outlets.append({"source": l["source"], "url": l["url"]})
        stories.append({
            "title": top["title"], "url": top["url"], "source": top["source"],
            "published": top["published"], "summary": next((l["summary"] for l in ls if l["summary"]), ""),
            "celebrities": sorted({c for l in ls for c in l["celebrities"]}),
            "outlets": outlets,
            "batch": min((l.get("batch") or "Earlier" for l in ls), key=lambda b: (b != "Earlier", b)),
        })
    stories.sort(key=lambda x: x["published"] or "", reverse=True)
    return stories


def read_articles():
    out = []
    for f in sorted((ROOT / "articles").glob("*.md")):
        front = f.read_text().split("---")[1] if f.read_text().startswith("---") else ""
        get = lambda k: (re.search(rf"^{k}: ?(.*)$", front, re.M) or [None, ""])[1].strip().strip('"')  # noqa: E731
        out.append({"path": f"articles/{f.name}", "title": get("title"), "status": get("status"), "wp_status": get("wp_status") or "draft",
                    "batch": get("batch"), "celebrity": get("celebrity"), "wp_link": get("wp_link")})
    return out


usage_file = ROOT / "data" / "usage.json"
usage = json.loads(usage_file.read_text()) if usage_file.exists() else {}
stories = group(leads)
data = {
    "country": cfg["country"],
    "timezone": cfg.get("timezone", "UTC"),
    "interval_hours": cfg.get("interval_hours", 3),
    "last_run": usage.get("last_run"),
    "profiles": cfg.get("profiles", {}),
    "runs_this_month": usage.get(datetime.now(timezone.utc).strftime("%Y-%m"), 0),
    "lead_count": len(leads),
    "articles": read_articles(),
    "celebrities": cfg["celebrities"],
    "paused": bool(cfg.get("paused")),
    "updated": datetime.now(timezone.utc).isoformat(),
    "leads": stories,
}

TEMPLATE = r"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="robots" content="noindex,nofollow,noarchive">
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
.tabs{display:flex;gap:6px;overflow-x:auto;margin:6px 0 12px}.tab{white-space:nowrap;padding:6px 12px;border-radius:8px 8px 0 0;border:1px solid var(--line);border-bottom:2px solid var(--line);background:var(--card);cursor:pointer;font-size:13px}.tab.on{border-bottom-color:var(--acc);font-weight:700}
.profiles{display:flex;gap:12px;overflow-x:auto;margin:6px 0 14px}.prof{min-width:190px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;text-align:center}.prof .pav{width:84px;height:84px;font-size:20px;border-radius:50%;margin:0 auto 6px;display:grid;place-items:center;color:#fff;font-weight:700;background-size:cover;background-position:center}.prof b{display:block;font-size:14px;cursor:pointer}.icos{display:flex;justify-content:center;gap:6px;margin-top:8px}.ico{display:grid;place-items:center;width:28px;height:28px;border-radius:50%;border:1px solid var(--line)}.ico img{width:14px;height:14px}.ico.off{opacity:.25}@media(prefers-color-scheme:dark){.ico img{filter:invert(1)}}
.also{font-size:12px;color:var(--mut)}.cnt{font-size:11px;font-weight:700;background:var(--accbg);color:var(--ink);border-radius:99px;padding:2px 8px}
.navlink{margin-left:auto;color:#e3b341;font-size:14px;background:transparent;border:1px solid #e3b34166}dialog{width:min(640px,94vw);max-height:90vh;overflow:auto;border:1px solid var(--line);border-radius:14px;background:var(--card);color:var(--ink);padding:0}dialog::backdrop{background:#000a}.dh{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-bottom:1px solid var(--line);font-size:17px}.dtabs{display:flex;gap:6px;padding:10px 16px 0}.dt.on{background:var(--ink);color:var(--bg)}.dp{padding:6px 16px 16px}.step{display:flex;gap:12px;margin:14px 0}.n{flex:none;width:26px;height:26px;border-radius:50%;background:var(--acc);color:#111;display:grid;place-items:center;font-weight:700;font-size:13px}.cp{display:flex;gap:8px;align-items:flex-start;margin:6px 0 10px}.cp code{flex:1;display:block;padding:8px 10px}.btn{display:inline-block;margin-top:6px;padding:6px 12px;border-radius:8px;border:1px solid var(--line);font-size:14px}code{background:var(--accbg);padding:2px 6px;border-radius:6px;word-break:break-all;font-size:13px}.arow{display:flex;flex-wrap:wrap;gap:10px;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin-bottom:8px}.arow .nm{font-weight:600;min-width:150px}.chip2{font-size:12px;font-weight:700;border-radius:99px;padding:3px 10px;background:var(--accbg)}.chip2.ok{background:#2f855a;color:#fff}.chip2.no{background:#c53030;color:#fff}.arow .sp{flex:1}.arow button,.arow select,.arow a.btn{padding:5px 10px;font-size:13px;margin:0}
.empty{color:var(--mut);padding:30px;text-align:center}
footer{color:var(--mut);font-size:12px;padding:30px 0}
</style>
<header><div class="wrap"><div class="brand" style="width:100%"><div class="logo">MC</div>
<div><h1>Modus Carry · __COUNTRY__ Celebrity News</h1><div class="sub" id="upd"></div></div><button id="conn" class="navlink">Connect Claude / WordPress</button></div></div></header>
<main class="wrap">
<div class="panel"><div><div id="state"></div><div id="timer"></div></div>
<div><button class="pri" id="run">Run now</button> <button id="pause"></button> <button id="add">+ Add celebrity</button> <button id="tok" title="GitHub token">🔑</button></div>
<button id="sched">Change interval</button>
<div id="msg"></div><div id="usage" class="also"></div></div>
<div class="tools"><input id="q" type="search" placeholder="Search headlines…">
<select id="src"><option value="">All sources</option></select>
<select id="sort"><option value="new">Newest first</option><option value="cel">Group by celebrity</option><option value="src">Group by source</option></select>
<select id="when"><option value="">Any time</option><option value="3">Last 3 hours</option><option value="24">Last 24 hours</option><option value="72">Last 3 days</option></select></div>
<div class="profiles" id="profiles"></div>
<div class="chips" id="chips"></div>
<div class="tabs" id="tabs"></div>
<div id="top"></div><div id="list"></div>

<dialog id="dlg"><div class="dh"><b>Connect</b><button id="dclose" aria-label="Close">✕</button></div>
<div class="dtabs"><button class="dt on" data-t="claude">Claude</button><button class="dt" data-t="wp">WordPress</button></div>
<div id="p-claude" class="dp">
<p class="also">No server needed. Everything lives in this GitHub repo and GitHub has its own MCP server. Works with any Claude account.</p>
<div class="step"><span class="n">1</span><div><b>Make a GitHub token</b> (once)<br>GitHub → Settings → Developer settings → Fine-grained tokens. Repository: <code>Researcher-agents</code> only. Permissions: <b>Contents</b> and <b>Actions</b> = Read and write.
<br><a class="btn" href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener">Open token page ↗</a></div></div>
<div class="step"><span class="n">2</span><div><b>Add the connector</b><br>
<b>claude.ai or Desktop:</b> Settings → Connectors → Add custom connector → paste:
<div class="cp"><code>https://api.githubcopilot.com/mcp/</code><button class="copy">Copy</button></div>
<b>Claude Code:</b> run this (replace YOUR_TOKEN):
<div class="cp"><code>claude mcp add --transport http github https://api.githubcopilot.com/mcp/ --header "Authorization: Bearer YOUR_TOKEN"</code><button class="copy">Copy</button></div></div></div>
<div class="step"><span class="n">3</span><div><b>Tell Claude</b> to start:
<div class="cp"><code>Open MirzaNumanBaig/Researcher-agents and follow CLAUDE.md. Check the latest batch and draft the roundup article.</code><button class="copy">Copy</button></div>
<span class="also">To change accounts later, repeat steps 2 and 3 on the new account.</span></div></div>
</div>
<div id="p-wp" class="dp" hidden>
<p class="also">GitHub sends approved articles to moduscarry.com. Claude never publishes by itself.</p>
<div class="step"><span class="n">1</span><div><b>Create an application password</b><br>WordPress admin → Users → Profile → Application Passwords → name it <code>Researcher-agents</code> → Add. Copy the password it shows.</div></div>
<div class="step"><span class="n">2</span><div><b>Add 3 secrets</b> in the repo: Settings → Secrets and variables → Actions<br><code>WP_URL</code> = https://moduscarry.com<br><code>WP_USER</code> = your WordPress username<br><code>WP_APP_PASSWORD</code> = the password from step 1
<br><a class="btn" href="https://github.com/MirzaNumanBaig/Researcher-agents/settings/secrets/actions" target="_blank" rel="noopener">Open secrets page ↗</a></div></div>
<div class="step"><span class="n">3</span><div><b>How articles flow</b><br>Claude saves a draft → you approve it → GitHub posts it with the status you chose: <b>draft</b>, <b>pending</b> (review) or <b>publish</b>. Change the status later and the same post is updated.</div></div>
</div></dialog>
<footer>Headlines come from Google News and Australian entertainment feeds. Google News does not provide images or full summaries; open a story for the full article. Profile photos and links: Wikidata / Wikimedia Commons.</footer>
</main>
<script>
const D=__DATA__,REPO="MirzaNumanBaig/Researcher-agents";
const $=i=>document.getElementById(i),esc=s=>String(s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let paused=D.paused,celeb="",batch="";
const COL=["#b8860b","#2b6cb0","#2f855a","#c05621","#6b46c1","#b83280","#2c7a7b"];
const col=n=>COL[[...n].reduce((a,c)=>a+c.charCodeAt(0),0)%COL.length];
const ini=n=>n.split(/\s+/).map(w=>w[0]).slice(0,2).join("").toUpperCase();
const ago=d=>{const m=Math.round((Date.now()-new Date(d))/6e4);if(m<1)return"just now";if(m<60)return m+"m ago";if(m<1440)return Math.round(m/60)+"h ago";return Math.round(m/1440)+"d ago"};
const age=l=>l.published?(Date.now()-new Date(l.published))/36e5:1e9;
$("upd").textContent=D.leads.length+" stories ("+D.lead_count+" headlines) · updated "+ago(D.updated);
[...new Set(D.leads.flatMap(l=>l.outlets.map(o=>o.source)).filter(Boolean))].sort().forEach(s=>$("src").add(new Option(s,s)));
function chips(){const c=[["","All"],...D.celebrities.map(n=>[n,n])];
$("chips").innerHTML=c.map(([v,t])=>'<button class="chip'+(v===celeb?' on':'')+'" data-v="'+esc(v)+'">'+esc(t)+'</button>').join("");
document.querySelectorAll(".chip").forEach(b=>b.onclick=()=>{celeb=b.dataset.v;chips();render()})}
function tabs(){const bs=[...new Set(D.leads.map(l=>l.batch))].sort().reverse();
$("tabs").innerHTML=[["","All batches"],["__articles","Articles ("+D.articles.length+")"],...bs.map(b=>[b,b==="Earlier"?"Earlier":b.slice(5)])].map(([v,t])=>'<button class="tab'+(v===batch?' on':'')+'" data-v="'+esc(v)+'" title="'+esc(v?"Found in the run at "+v+" ("+D.timezone+")":"")+'">'+esc(t)+(v&&v!=="__articles"?' ('+D.leads.filter(l=>l.batch===v).length+')':'')+'</button>').join("");
document.querySelectorAll(".tab").forEach(b=>b.onclick=()=>{batch=b.dataset.v;tabs();render()})}
const ICONS={instagram:"instagram",tiktok:"tiktok",x:"x",facebook:"facebook",youtube:"youtube",website:"googlechrome"};
function profiles(){$("profiles").innerHTML=D.celebrities.map(n=>{const p=D.profiles[n]||{};
return '<div class="prof"><div class="pav" style="background-color:'+col(n)+(p.photo?';background-image:url('+esc(p.photo)+')':'')+'">'+(p.photo?'':esc(ini(n)))+'</div><b data-n="'+esc(n)+'">'+esc(n)+'</b>'+'<div class="icos">'+Object.keys(ICONS).map(k=>p[k]?'<a class="ico" href="'+esc(p[k])+'" target="_blank" rel="noopener" title="'+k+'"><img alt="'+k+'" src="https://cdn.jsdelivr.net/npm/simple-icons@11.14.0/icons/'+ICONS[k]+'.svg"></a>':'<span class="ico off" title="'+k+': not added yet"><img alt="" src="https://cdn.jsdelivr.net/npm/simple-icons@11.14.0/icons/'+ICONS[k]+'.svg"></span>').join("")+'</div>'+'</div>'}).join("");
document.querySelectorAll(".prof b").forEach(b=>b.onclick=()=>{celeb=b.dataset.n;chips();render()})}
const slug=s=>s.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"");
const BLOB="https://github.com/"+REPO+"/blob/main/";
async function editArticle(path,fn){const f=await gh("/contents/"+path);let t=decodeURIComponent(escape(atob(f.content.replace(/\n/g,""))));t=fn(t);
await gh("/contents/"+path,{method:"PUT",body:JSON.stringify({message:"Dashboard: update "+path,sha:f.sha,content:btoa(unescape(encodeURIComponent(t)))})})}
const setKey=(k,v)=>t=>t.replace(new RegExp("^"+k+": .*$","m"),k+": "+v);
function statusChip(a){if(!a)return'<span class="chip2">Not written yet</span>';
const m={pending:["Draft · awaiting approval",""],approved:["Approved · sending to WordPress","ok"],sent:["Sent to WordPress ("+a.wp_status+")","ok"],rejected:["Rejected","no"]}[a.status]||[a.status,""];
return'<span class="chip2 '+m[1]+'">'+esc(m[0])+'</span>'}
function artRow(a,celeb,b,n){const p="Open "+REPO+" and follow CLAUDE.md. Write the article for "+celeb+" from batch "+b+" (briefs/"+slug(b)+"/"+slug(celeb)+".json) and save it as a pending draft.";
let h='<div class="arow"><span class="nm">'+esc(celeb)+(n!=null?' <span class="also">· '+n+' stories</span>':'')+'</span>'+statusChip(a)+'<span class="sp"></span>';
if(!a)h+='<button data-prompt="'+esc(p)+'">Copy Claude prompt</button>';
else{h+='<a class="btn" href="'+BLOB+esc(a.path)+'" target="_blank" rel="noopener">Read</a>';
if(a.status==="pending")h+='<select data-wp="'+esc(a.path)+'">'+["draft","pending","publish"].map(x=>'<option value="'+x+'"'+(x===a.wp_status?" selected":"")+'>WordPress: '+(x==="pending"?"review":x)+'</option>').join("")+'</select><button data-act="approved" data-path="'+esc(a.path)+'">Approve</button><button data-act="rejected" data-path="'+esc(a.path)+'">Reject</button>';
if(a.status==="sent"){h+='<select data-wp="'+esc(a.path)+'">'+["draft","pending","publish"].map(x=>'<option value="'+x+'"'+(x===a.wp_status?" selected":"")+'>WordPress: '+(x==="pending"?"review":x)+'</option>').join("")+'</select>';if(a.wp_link)h+='<a class="btn" href="'+esc(a.wp_link)+'" target="_blank" rel="noopener">View post</a>'}}
return h+'</div>'}
function wireArt(root){root.querySelectorAll("[data-prompt]").forEach(b=>b.onclick=()=>{navigator.clipboard.writeText(b.dataset.prompt);say("Prompt copied. Paste it into Claude.")});
root.querySelectorAll("[data-act]").forEach(b=>b.onclick=async()=>{try{await editArticle(b.dataset.path,setKey("status",b.dataset.act));say(b.dataset.act==="approved"?"Approved. GitHub will send it to WordPress in about a minute. Refresh later.":"Rejected.")}catch(e){say("Failed: "+e.message)}});
root.querySelectorAll("[data-wp]").forEach(s=>s.onchange=async()=>{try{await editArticle(s.dataset.wp,setKey("wp_status",s.value));say("WordPress status set to "+s.value+(".")+" It applies once the article is approved/sent.")}catch(e){say("Failed: "+e.message)}})}
function articlePanel(b){const per={};D.leads.filter(l=>l.batch===b).forEach(l=>l.celebrities.forEach(c=>per[c]=(per[c]||0)+1));
const rows=D.celebrities.filter(c=>per[c]).map(c=>artRow(D.articles.find(a=>a.batch===b&&a.celebrity===c),c,b,per[c])).join("");
return'<h2>Blog articles for this batch</h2>'+(rows||'<div class="empty">No stories for tracked celebrities in this batch.</div>')}
function card(l,hero){const n=(l.celebrities||[])[0]||"";
return '<a class="card'+(hero?' hero':'')+'" href="'+esc(l.url)+'" target="_blank" rel="noopener"><div class="top"><div class="av" style="background:'+col(n)+'">'+esc(ini(n))+'</div><div><div class="who">'+esc((l.celebrities||[]).join(", "))+'</div><div class="meta">'+esc(l.source)+' · '+(l.published?ago(l.published):"")+'</div></div>'+(age(l)<=3?'<span class="badge">NEW</span>':'')+'</div><h3>'+esc(l.title)+'</h3>'+(l.outlets.length>1?'<div class="also"><span class="cnt">'+l.outlets.length+' outlets</span> '+esc(l.outlets.slice(0,5).map(o=>o.source).join(", "))+(l.outlets.length>5?" +"+(l.outlets.length-5):"")+'</div>':'')+(l.summary?'<p>'+esc(l.summary.slice(0,220))+'</p>':'')+'</a>'}
function render(){
const q=$("q").value.toLowerCase(),s=$("src").value,w=+$("when").value,so=$("sort").value;
let ls=D.leads.filter(l=>(!celeb||(l.celebrities||[]).includes(celeb))&&(!s||l.outlets.some(o=>o.source===s))&&(!batch||l.batch===batch)&&(!q||(l.title+" "+l.summary+" "+l.outlets.map(o=>o.source).join(" ")).toLowerCase().includes(q))&&(!w||age(l)<=w));
ls.sort((a,b)=>(b.published||"").localeCompare(a.published||""));
const plain=!q&&!s&&!w&&!celeb&&!batch&&so==="new";
if(batch==="__articles"){$("top").innerHTML="";$("list").innerHTML='<h2>All articles ('+D.articles.length+')</h2>'+(D.articles.map(a=>artRow(a,a.celebrity||a.title,a.batch)).join("")||'<div class="empty">No articles yet. Open a batch tab and ask Claude to write them.</div>');wireArt($("list"));return}
$("top").innerHTML=plain&&ls.length?'<h2>★ Top stories</h2><div class="grid">'+ls.slice(0,3).map(l=>card(l,1)).join("")+'</div>':"";
if(plain)ls=ls.slice(3);
if(batch&&so==="new"){$("top").innerHTML=articlePanel(batch);wireArt($("top"))}
if(!ls.length&&!plain){$("list").innerHTML='<div class="empty">No stories match.</div>';return}
if(so==="new"){$("list").innerHTML='<h2>Latest ('+ls.length+')</h2><div class="grid">'+ls.map(l=>card(l)).join("")+'</div>';return}
const key=l=>so==="cel"?((l.celebrities||[])[0]||"Other"):(l.source||"Other"),g={};
ls.forEach(l=>(g[key(l)]=g[key(l)]||[]).push(l));
$("list").innerHTML=Object.keys(g).sort().map(k=>'<h2>'+esc(k)+' ('+g[k].length+')</h2><div class="grid">'+g[k].map(l=>card(l)).join("")+'</div>').join("")}
["q","src","sort","when"].forEach(i=>$(i).oninput=render);
function nextRun(){if(!D.last_run)return null;return new Date(new Date(D.last_run).getTime()+D.interval_hours*36e5)}
function tick(){$("state").textContent=paused?"⏸ Paused: scheduled runs are off":"▶ Runs every "+D.interval_hours+" hours";$("pause").textContent=paused?"Continue":"Pause";
if(paused){$("timer").textContent="Next run: none (paused)";return}
const nr=nextRun();if(!nr){$("timer").textContent="Waiting for the first run";return}const ms=nr-new Date();if(ms<=0){$("timer").textContent="Due now: waiting for GitHub to start it (can take a few minutes)";return}const h=Math.floor(ms/36e5),m=Math.floor(ms%36e5/6e4),s=Math.floor(ms%6e4/1e3);
$("timer").textContent="Next run in "+h+"h "+m+"m "+s+"s (approx.; GitHub can start a few minutes late)"}
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
$("usage").textContent="Runs this month: "+D.runs_this_month+" · GitHub Actions minutes: unlimited (public repo) · Claude plan usage: see claude.ai/settings/usage";
$("sched").onclick=async()=>{const v=prompt("Run every how many hours? (1-24)",D.interval_hours);if(v===null)return;const n=parseInt(v,10);if(!(n>=1&&n<=24)){say("Enter a number from 1 to 24.");return}try{await editCfg(c=>{c.interval_hours=n;delete c.run_hours});D.interval_hours=n;tick();say("Saved. Runs every "+n+" hours, counted from the last run.")}catch(e){say("Failed: "+e.message)}};
$("conn").onclick=()=>$("dlg").showModal();$("dclose").onclick=()=>$("dlg").close();
$("dlg").onclick=e=>{if(e.target===$("dlg"))$("dlg").close()};
document.querySelectorAll(".dt").forEach(b=>b.onclick=()=>{document.querySelectorAll(".dt").forEach(x=>x.classList.toggle("on",x===b));$("p-claude").hidden=b.dataset.t!=="claude";$("p-wp").hidden=b.dataset.t!=="wp"});
document.querySelectorAll(".copy").forEach(b=>b.onclick=()=>{navigator.clipboard.writeText(b.previousElementSibling.textContent);b.textContent="Copied";setTimeout(()=>b.textContent="Copy",1500)});
chips();profiles();tabs();render();tick();
</script></html>"""

page = (TEMPLATE.replace("__COUNTRY__", cfg["country"])
        .replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))
(ROOT / "data" / "stories.json").write_text(json.dumps(stories, indent=2, ensure_ascii=False))  # read by the MCP server
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs" / "index.html").write_text(page)
print("dashboard built")
