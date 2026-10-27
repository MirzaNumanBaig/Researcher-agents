---
name: project-state-2026-10
description: State of Researcher-agents as of 2026-10-27 - what shipped, what is pending, what the user must do
type: project
---

Shipped and on `main` (all via branches then merge): publish fix (WordPress 400 from reading only 100 tags), publish fallback + failure-alert issue + tests, per-article image links, better source reading (cookie walls, JSON-LD, up to 5 outlets), dashboard Last-48-hours / Archive tabs with article-state chips, 30-day cleanup (`keep_days: 30`, `dashboard_hours: 48`), push retry script, wrapped actor picker with search (PR #6), 40 tracked actors (25 added; surnames Fox/Oh/Short/Williams/Anderson need full-name match), image generation only for approved / just-sent articles, FLUX model support plus a manual `test-image-model.yml` workflow.

Decisions made 2026-10-27:
- Featured-image model is **FLUX.1 schnell** (`@cf/black-forest-labs/flux-1-schnell`), chosen by the user after the sample comparison (klein 4B was the close second; DreamShaper looked bad). It is the code default (`MODEL` in agents/generate_images.py); the sending workflows do not pass a `CF_IMAGE_MODEL` secret, so a secret of that name has no effect. `ai_images` is turned on in the same change.
- Memory lives in the repo at `.claude/memory/` (the cloud container is temporary), loaded by `CLAUDE.md` and `.claude/rules/memory.md`. The repo is public: never put secrets in memory.

Pending / open:
- Merge the branch that turns schnell images on; after it, recent sent posts (under 48 hours old) without an image get one on the next run, and posts then carry featured images.
- PR #5 (klein4b + featured-image skill) is open and conflicts with `main`; offer to rebase it (it would then only add the skill and prompt tweaks) or close it.
- 12 merged remote branches are still on GitHub (deletion is blocked from this sandbox); the user can delete them. Only feature/klein4b-featured-images must stay.
- The "Fill profiles" workflow was dispatched on 2026-10-26 and had not started (queued behind the long writer run on the shared `repo-writes` lock). Photos for the 25 new actors depend on it.
- Writer is a single Claude account; many actors can hit its usage limit.

**Why:** Context for resuming without re-deriving it.

**How to apply:** Start by checking whether these items were finished; the dates are 2026-10-26/27, so they may be stale.
