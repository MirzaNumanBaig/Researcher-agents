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
