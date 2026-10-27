---
name: reference-new-chat-prompt
description: The prompt the user pastes to start a new chat so Claude loads the repo memory and continues the work
type: reference
---

A new chat cannot read old conversations. Continuity comes from the repo: `CLAUDE.md` -> `AGENTS.md` (how the system works) and `.claude/memory/` (decisions, preferences, pending work). Start prompt:

```
Continue work on the Researcher-agents repo (MirzaNumanBaig/Researcher-agents). First read AGENTS.md and the memory index at .claude/memory/MEMORY.md, then every memory file it lists (the index loads automatically through CLAUDE.md), especially project-state-2026-10.md and the feedback files. Check the current state of main, open PRs and the latest workflow runs, then tell me in five lines what is done, what is pending, and what you recommend next. Follow my working style from memory: branch, test, ask before merging to main. If something in memory looks out of date, verify it and update the memory.
```

Access checklist for a new session (it only has what its environment gives it):
- Start it from the Claude Code UI with the repo MirzaNumanBaig/Researcher-agents selected, in the SAME cloud environment as before (same network policy). If the repo is not attached, call `add_repo` with `access: push`; the user must approve it (the auto-mode check blocked it until they did; they can add a permission rule for `mcp__claude-code-remote__add_repo` to avoid that).
- Repo-level GitHub secrets (CF_ACCOUNT_ID, CF_API_TOKEN, WP_*, CLAUDE_CODE_OAUTH_TOKEN) are used by the workflows, not the session, so nothing needs re-adding.
- Always blocked in this kind of sandbox: listing secrets, changing repo settings, deleting branches, GraphQL. Use the REST routes in `reference-sandbox-and-apis.md`; ask the user for those actions.
- Quick self-test: `git ls-remote origin`, `gh api repos/MirzaNumanBaig/Researcher-agents/actions/runs --jq '.workflow_runs[0].status'`, and push a test branch only if a change is planned.

**How to apply:** Offer this prompt when the user starts over, and keep it in sync if the memory layout changes.
