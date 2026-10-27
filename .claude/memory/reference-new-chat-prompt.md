---
name: reference-new-chat-prompt
description: The prompt the user pastes to start a new chat so Claude loads the repo memory and continues the work
type: reference
---

A new chat cannot read old conversations. Continuity comes from the repo: `CLAUDE.md` -> `AGENTS.md` (how the system works) and `.claude/memory/` (decisions, preferences, pending work). Start prompt:

```
Continue work on the Researcher-agents repo (MirzaNumanBaig/Researcher-agents). First read AGENTS.md and the memory index at .claude/memory/MEMORY.md, then every memory file it lists, especially project-state-2026-10.md and the feedback files. Check the current state of main, open PRs and the latest workflow runs, then tell me in five lines what is done, what is pending, and what you recommend next. Follow my working style from memory: branch, test, ask before merging to main. If something in memory looks out of date, verify it and update the memory.
```

**How to apply:** Offer this prompt when the user starts over, and keep it in sync if the memory layout changes.
