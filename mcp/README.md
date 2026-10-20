# Connect any Claude account (always-online MCP) + WordPress

Everything runs online: a free **Cloudflare Worker** hosts the MCP server, **GitHub** holds all data and sends
approved articles to **WordPress**. Claude only writes. Nothing runs on your computer.

## A. Deploy the online MCP server (one time, ~10 min)
1. Free account at cloudflare.com. Note your **Account ID** (Workers & Pages page, right side).
2. Cloudflare → My Profile → API Tokens → Create Token → template **Edit Cloudflare Workers**. Copy the token.
3. GitHub → Settings → Developer settings → Fine-grained tokens → new token: repo `Researcher-agents` only,
   **Contents** + **Actions** = Read and write.
4. Make up a long random string (e.g. 40 characters) for `MCP_SECRET`.
5. In the repo: Settings → Secrets and variables → Actions → add:
   `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `MCP_GH_TOKEN` (the GitHub token), `MCP_SECRET`.
6. Actions tab → **Deploy MCP server** → Run workflow. It prints the worker address
   `https://researcher-agents-mcp.<your-subdomain>.workers.dev`.
7. Your connector URL is `https://researcher-agents-mcp.<your-subdomain>.workers.dev/mcp/<MCP_SECRET>`.
   Put it in `config.json` as `"mcp_url"` so the dashboard shows a Copy button (or tell Claude to do it).

## B. Add it to Claude (any account)
claude.ai → Settings → Connectors → Add custom connector → paste the URL. Repeat on another account any time.
The URL is a secret: anyone who has it can control the system. Change `MCP_SECRET` and redeploy to rotate it.

## C. Connect WordPress (moduscarry.com)
1. WordPress admin → Users → your profile → **Application Passwords** → create one named `Researcher-agents`.
2. Repo secrets: `WP_URL` (`https://moduscarry.com`), `WP_USER` (your WP username), `WP_APP_PASSWORD`.
3. Flow: Claude `save_draft` → you review → `set_draft_status approved` → GitHub sends it to WordPress with the
   article's `wp_status`: `draft`, `pending` (review) or `publish`. Change it later with `set_wp_status` and GitHub
   updates the same post. Nothing is sent unless the article is `approved`.

## Local alternative
`mcp/server.py` is the same tools as a local stdio server (`claude mcp add researcher-agents -e GITHUB_TOKEN=... -- python3 mcp/server.py`).

Tools: get_status, list_batches, get_stories, run_now, set_paused, set_interval, add_celebrity, remove_celebrity,
save_draft, list_drafts, read_draft, set_draft_status, set_wp_status.
