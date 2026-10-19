# Connect any Claude account to this system

The server runs on your computer and talks only to the GitHub API. Claude does the writing; GitHub does everything else.

1. Create a **fine-grained GitHub token** (Settings → Developer settings → Fine-grained tokens): repository `Researcher-agents` only; permissions **Contents** and **Actions** = Read and write.
2. Download `mcp/server.py` (or clone the repo). Needs Python 3.9+, no packages.
3. Add it to Claude.

**Claude Code**
```
claude mcp add researcher-agents -e GITHUB_TOKEN=YOUR_TOKEN -- python3 /path/to/mcp/server.py
```

**Claude Desktop** (`claude_desktop_config.json`)
```json
{"mcpServers": {"researcher-agents": {
  "command": "python3", "args": ["/path/to/mcp/server.py"],
  "env": {"GITHUB_TOKEN": "YOUR_TOKEN"}}}}
```

Switching Claude accounts = repeat step 3 on that account. Nothing else changes.

Tools: get_status, list_batches, get_stories, run_now, set_paused, set_interval, add_celebrity, remove_celebrity,
save_draft, list_drafts, read_draft, set_draft_status.
