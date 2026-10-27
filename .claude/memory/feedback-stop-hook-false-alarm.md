---
name: feedback-stop-hook-false-alarm
description: The stop-hook "unpushed commit / no remote branch" warning was wrong almost every time; verify with git ls-remote
type: feedback
---

`~/.claude/stop-hook-git-check.sh` repeatedly said a branch had unpushed commits and "no remote branch" right after a successful push. Each time `git ls-remote --heads origin <branch>` showed the remote tip equal to `git rev-parse HEAD`.

**Why:** Pushes were done with `-q -u` and the hook apparently reads tracking info that was not set, or a stale state.

**How to apply:** When the hook fires, verify with `git ls-remote --heads origin <branch>` and `git rev-parse HEAD`, and `git status --short`. If equal and clean, tell the user in one short line that it is a false alarm. Two cases were genuinely real: uncommitted `data/articles.json` after a local dashboard build (discard it with `git checkout`), and a branch deleted by auto-delete after a PR merge (delete the local copy).
