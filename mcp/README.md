# Connect any Claude account

No server to run or host. All data and settings are files in this GitHub repo, and GitHub has its own MCP server.

1. Create a **fine-grained GitHub token**: Settings > Developer settings > Fine-grained tokens, repository
   `Researcher-agents` only, **Contents** and **Actions** = Read and write.
2. Add GitHub's MCP server to Claude (URL: `https://api.githubcopilot.com/mcp/`):
   - Claude Code: `claude mcp add --transport http github https://api.githubcopilot.com/mcp/ --header "Authorization: Bearer YOUR_TOKEN"`
   - claude.ai / Desktop: Settings > Connectors > Add custom connector > paste the URL, then sign in with GitHub if asked.
3. Tell Claude: "Open MirzaNumanBaig/Researcher-agents and follow CLAUDE.md." The repo's `CLAUDE.md` explains how
   to read stories, change settings and write articles, so a new account needs nothing else.

WordPress (moduscarry.com): create an Application Password (WP admin > Users > Profile), then add repo secrets
`WP_URL`, `WP_USER`, `WP_APP_PASSWORD`. GitHub sends `approved` articles with their `wp_status`.

Optional: `mcp/server.py` is a local server with friendlier tool names for the same actions (needs `GITHUB_TOKEN`).

## Claude Code cloud sessions (paste the token once)
The repo's `.mcp.json` starts `mcp/server.py` in every Claude Code session opened on this repo. It contains no token: it reads
`GH_TOKEN` from the session's environment.
1. Create a fine-grained token (Researcher-agents, plus any other repos you want; Contents, Actions, Workflows, Pull requests = Read and write).
2. In the Claude app, open the cloud environment (session title bar > environment > Edit) and set the environment variable
   `GH_TOKEN=<your token>`. Every new session with that environment gets it; `gh` and `git push` use it too.
3. Start a session on this repo and approve the `researcher-agents` MCP server if asked. When the token expires, repeat step 1-2.

## Without connecting GitHub to Claude (token only)
Use this when you do not want to link your GitHub account to a Claude account. The token is the only link.
1. Create a fine-grained token (this repo only; Contents + Actions = Read and write). Never paste it into a chat.
2. Add the local server to Claude Code on a computer or Codespace:
   `claude mcp add github-repo -e GITHUB_TOKEN=YOUR_TOKEN -- python3 /path/to/Researcher-agents/mcp/server.py`
   It talks to `api.github.com` only. Tools include `read_repo_file` / `write_repo_file`, so the account can change the dashboard
   (`agents/build_dashboard.py`) and everything else.
3. In Claude cloud sessions, `api.githubcopilot.com` is blocked by default. Either add it under the environment's Network access
   (Allowed domains), or use this local server, which only needs `api.github.com`.
