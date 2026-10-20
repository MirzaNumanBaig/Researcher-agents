// Remote MCP server for Cloudflare Workers (free tier). Same tools as mcp/server.py, but always online:
// add its URL as a custom connector in any Claude account. State lives in the GitHub repo.
// Secrets: GH_TOKEN (fine-grained, this repo: Contents + Actions read/write), MCP_SECRET (random string used in the URL).
const REPO = "MirzaNumanBaig/Researcher-agents";
const API = `https://api.github.com/repos/${REPO}`;

async function gh(env, path, method = "GET", body) {
  const r = await fetch(API + path, {
    method,
    headers: { ...(env.GH_TOKEN ? { Authorization: `Bearer ${env.GH_TOKEN}` } : {}), Accept: "application/vnd.github+json", "User-Agent": "researcher-agents-mcp", "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`GitHub ${r.status}: ${(await r.text()).slice(0, 200)}`);
  const t = await r.text();
  return t ? JSON.parse(t) : null;
}
const b64d = (s) => new TextDecoder().decode(Uint8Array.from(atob(s.replace(/\n/g, "")), (c) => c.charCodeAt(0)));
const b64e = (s) => { const b = new TextEncoder().encode(s); let x = ""; b.forEach((c) => (x += String.fromCharCode(c))); return btoa(x); };
async function readFile(env, path) { const f = await gh(env, `/contents/${path}`); return [b64d(f.content), f.sha]; }
async function writeFile(env, path, text, message, sha) {
  await gh(env, `/contents/${path}`, "PUT", { message, content: b64e(text), ...(sha ? { sha } : {}) });
}
async function editConfig(env, fn, message) {
  const [t, sha] = await readFile(env, "config.json");
  const cfg = JSON.parse(t); fn(cfg);
  await writeFile(env, "config.json", JSON.stringify(cfg, null, 2) + "\n", message, sha);
  return cfg;
}
const stories = async (env) => JSON.parse((await readFile(env, "data/stories.json"))[0]);
const slugify = (t) => t.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60);
const WP = ["draft", "pending", "publish", "private"];

const tools = {
  get_status: ["Schedule, pause state, celebrities, last run and recent GitHub Actions runs.", {}, async (env) => {
    const cfg = JSON.parse((await readFile(env, "config.json"))[0]);
    const usage = JSON.parse((await readFile(env, "data/usage.json"))[0]);
    const runs = (await gh(env, "/actions/runs?per_page=5")).workflow_runs;
    return { country: cfg.country, celebrities: cfg.celebrities, paused: !!cfg.paused, interval_hours: cfg.interval_hours || 3,
      last_run_utc: usage.last_run, recent_workflow_runs: runs.map((r) => `${r.created_at} ${r.name} ${r.conclusion || r.status}`) };
  }],
  list_batches: ["Run batches (one per collection run) with story counts.", {}, async (env) => {
    const out = {}; (await stories(env)).forEach((s) => (out[s.batch] = (out[s.batch] || 0) + 1));
    return Object.fromEntries(Object.entries(out).sort().reverse());
  }],
  get_stories: ["Grouped news stories (all outlets + links). Filter by batch label and/or celebrity.", { batch: "string", celebrity: "string", limit: "integer" },
    async (env, a) => (await stories(env)).filter((s) => (!a.batch || s.batch === a.batch) && (!a.celebrity || s.celebrities.includes(a.celebrity))).slice(0, a.limit || 30)],
  run_now: ["Start a collection run immediately.", {}, async (env) => { await gh(env, "/actions/workflows/collect.yml/dispatches", "POST", { ref: "main" }); return "Collection run started."; }],
  set_paused: ["Pause or resume scheduled runs.", { paused: "boolean" }, async (env, a) => { await editConfig(env, (c) => (c.paused = !!a.paused), "MCP: set paused"); return `paused = ${!!a.paused}`; }],
  set_interval: ["Set hours between runs (1-24).", { hours: "integer" }, async (env, a) => {
    if (!(a.hours >= 1 && a.hours <= 24)) throw new Error("hours must be 1-24");
    await editConfig(env, (c) => (c.interval_hours = a.hours), "MCP: set interval"); return `interval_hours = ${a.hours}`;
  }],
  add_celebrity: ["Start tracking a celebrity.", { name: "string" }, async (env, a) =>
    (await editConfig(env, (c) => { if (!c.celebrities.includes(a.name)) c.celebrities.push(a.name); (c.profiles = c.profiles || {})[a.name] = c.profiles[a.name] || {}; }, `MCP: add ${a.name}`)).celebrities],
  remove_celebrity: ["Stop tracking a celebrity.", { name: "string" }, async (env, a) =>
    (await editConfig(env, (c) => (c.celebrities = c.celebrities.filter((n) => n !== a.name)), `MCP: remove ${a.name}`)).celebrities],
  save_draft: ["Save an original article draft (markdown) with source URLs. Starts as pending approval. wp_status = what WordPress should set once approved: draft, pending (review) or publish.",
    { title: "string", body_markdown: "string", sources: "array", batch: "string", wp_status: "string" }, async (env, a) => {
      const wp = a.wp_status || "draft"; if (!WP.includes(wp)) throw new Error("wp_status must be draft, pending, publish or private");
      const stamp = (a.batch || new Date().toISOString().slice(0, 16)).replace(/[ :]/g, "-");
      const path = `articles/${stamp}-${slugify(a.title)}.md`;
      const front = `---\ntitle: ${JSON.stringify(a.title)}\nstatus: pending\nwp_status: ${wp}\nbatch: ${JSON.stringify(a.batch || "")}\nsources:\n${(a.sources || []).map((s) => `  - ${JSON.stringify(s)}\n`).join("")}---\n\n`;
      await writeFile(env, path, front + a.body_markdown + "\n", `MCP: draft ${slugify(a.title)}`); return path;
    }],
  list_drafts: ["List article drafts with approval and WordPress status.", {}, async (env) => {
    const items = await gh(env, "/contents/articles"); const out = [];
    for (const it of items.filter((i) => i.name.endsWith(".md"))) {
      const t = (await readFile(env, it.path))[0];
      const g = (k) => (t.match(new RegExp(`^${k}: (.*)$`, "m")) || [])[1] || "";
      out.push({ path: it.path, status: g("status"), wp_status: g("wp_status"), wp_link: g("wp_link"), title: g("title") });
    }
    return out;
  }],
  read_draft: ["Read one draft file.", { path: "string" }, async (env, a) => (await readFile(env, a.path))[0]],
  set_draft_status: ["Approve/reject a draft (pending, approved, rejected). Approved drafts are sent to WordPress by GitHub.", { path: "string", status: "string" }, async (env, a) => {
    if (!["pending", "approved", "rejected"].includes(a.status)) throw new Error("status must be pending, approved or rejected");
    const [t, sha] = await readFile(env, a.path);
    await writeFile(env, a.path, t.replace(/^status: .*/m, `status: ${a.status}`), `MCP: ${a.status} ${a.path}`, sha); return `${a.path} -> ${a.status}`;
  }],
  set_wp_status: ["Change what WordPress shows for a draft: draft, pending (review), publish or private. Applies to already-sent posts too.", { path: "string", wp_status: "string" }, async (env, a) => {
    if (!WP.includes(a.wp_status)) throw new Error("wp_status must be draft, pending, publish or private");
    const [t, sha] = await readFile(env, a.path);
    await writeFile(env, a.path, t.replace(/^wp_status: .*/m, `wp_status: ${a.wp_status}`), `MCP: wp_status ${a.wp_status} ${a.path}`, sha); return `${a.path} wp_status -> ${a.wp_status}`;
  }],
};

const schema = (props) => ({ type: "object", properties: Object.fromEntries(Object.entries(props).map(([k, v]) => [k, v === "array" ? { type: "array", items: { type: "string" } } : { type: v }])), additionalProperties: false });

async function rpc(env, msg) {
  switch (msg.method) {
    case "initialize": return { protocolVersion: msg.params?.protocolVersion || "2025-03-26", capabilities: { tools: {} }, serverInfo: { name: "researcher-agents", version: "1.0" } };
    case "tools/list": return { tools: Object.entries(tools).map(([name, [description, props]]) => ({ name, description, inputSchema: schema(props) })) };
    case "tools/call": {
      const t = tools[msg.params.name];
      if (!t) return { content: [{ type: "text", text: "Unknown tool" }], isError: true };
      try { const r = await t[2](env, msg.params.arguments || {}); return { content: [{ type: "text", text: typeof r === "string" ? r : JSON.stringify(r, null, 2) }] }; }
      catch (e) { return { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true }; }
    }
    case "ping": return {};
    default: return undefined;
  }
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (!env.MCP_SECRET || url.pathname !== `/mcp/${env.MCP_SECRET}`) return new Response("Not found", { status: 404 });
    if (req.method !== "POST") return new Response("POST JSON-RPC here", { status: 405 });
    const msg = await req.json();
    const batch = Array.isArray(msg) ? msg : [msg];
    const out = [];
    for (const m of batch) {
      if (m.id === undefined) continue;
      const result = await rpc(env, m);
      out.push(result === undefined ? { jsonrpc: "2.0", id: m.id, error: { code: -32601, message: "Method not found" } } : { jsonrpc: "2.0", id: m.id, result });
    }
    if (!out.length) return new Response(null, { status: 202 });
    return new Response(JSON.stringify(Array.isArray(msg) ? out : out[0]), { headers: { "Content-Type": "application/json" } });
  },
};
