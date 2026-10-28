---
name: project-state-2026-10
description: State of Researcher-agents as of 2026-10-27 - what shipped, what is pending, what the user must do
type: project
---

Shipped and on `main` (all via branches then merge): publish fix (WordPress 400 from reading only 100 tags), publish fallback + failure-alert issue + tests, per-article image links, better source reading (cookie walls, JSON-LD, up to 5 outlets), dashboard Last-48-hours / Archive tabs with article-state chips, 30-day cleanup (`keep_days: 30`, `dashboard_hours: 48`), push retry script, wrapped actor picker with search (PR #6), 40 tracked actors (25 added; surnames Fox/Oh/Short/Williams/Anderson need full-name match), image generation only for approved / just-sent articles, FLUX model support plus a manual `test-image-model.yml` workflow.

Decisions made 2026-10-27:
- Featured-image model is **FLUX.1 schnell** (`@cf/black-forest-labs/flux-1-schnell`), chosen by the user after the sample comparison (klein 4B was the close second; DreamShaper looked bad). It is the code default (`MODEL` in agents/generate_images.py); the sending workflows do not pass a `CF_IMAGE_MODEL` secret, so a secret of that name has no effect. `ai_images` is turned on in the same change.
- Memory lives in the repo at `.claude/memory/` (the cloud container is temporary), loaded by `CLAUDE.md` and `.claude/rules/memory.md`. The repo is public: never put secrets in memory.

- Dashboard Articles view now has status tabs (Pending review / Drafts / Published / To approve / Skipped & other) and each card shows the post's featured image (`wp_image`, synced from WordPress by publish_wordpress.py).

Merged to `main` 2026-10-27 23:07 UTC (commit fdf8dea): schnell is the default model, `ai_images` is true, dashboard cards show featured images with status tabs, memory lives in the repo. Tests, collect and Pages runs passed after the merge.

Article -> Image pipeline (branch feature/image-pipeline, NOT merged yet; user asked for it in a long spec): package `agents/imagegen/` (analyzer, concept rules, prompt writer, generator, checker, publisher, CLI `scripts/generate-image`), wired into generate_images.py with the old writer scene prompt as fallback. 76 tests pass on mocks. NOT yet proven with real Cloudflare output: on 2026-10-28 the account's 10,000 free neurons were used up (75 images in 3 minutes on 2026-10-27 23:11-23:14 UTC, a backfill burst), so the demo workflow only produced rule-based analyses and prompts. Retry: dispatch `image-pipeline-demo.yml` on the branch (`gh api -X POST .../actions/workflows/image-pipeline-demo.yml/dispatches -f ref=feature/image-pipeline`), download the artifact and show the user the analysis JSON, prompt and image of the 3 fictional samples. Unverified so far: LLM JSON quality, vision quality check (needs the user to accept Meta's licence once; never accept it for them), whether schnell honours width/height (it rejects `seed`).

Image pipeline v2 (branch feature/image-pipeline-v2, stacked on the whole pipeline, NOT merged, no PR yet; user asked 2026-10-28): output 1600x900 (generate 1536x864, upscale 2x Lanczos by default, Real-ESRGAN opt-in via IMG_UPSCALER), NO visible AI caption (IMG_CAPTION empty by default; AI flag only in articles/image-meta/*.json), scene_blueprint + 12 fictional stand-ins in agents/imagegen/cast.json, 90-150 word people prompt, scored vision check (1-5, reject under 4, 3 attempts then symbolic scene). Skill article-featured-image rewritten for it. 109 tests pass on mocks. Still NOT proven with real Cloudflare output: the allowance was spent on 2026-10-28 so the demo (image-pipeline-demo.yml, dispatch with ref=feature/image-pipeline-v2) gave only rule-based blueprints and prompts. Unverified: whether Cloudflare's schnell honours 1536x864 (it may ignore size), vision scores, Real-ESRGAN, face restoration.

Pending / open (verify each; they may be done by the time you read this):
- Check the FIRST real image run: the hourly publisher (:17 past the hour) and the writer run's publish step. Look at the `generate_images.py` lines in the logs (`N image(s) created, M failed`), then confirm the dashboard Articles cards show images. Recent sent posts (under 48 hours old) without an image should get one. If it fails (401/403/429), read the error body before changing anything; sample runs on 2026-10-27 proved the two Cloudflare secrets work.
- PR #5 (klein4b + featured-image skill) is open and conflicts with `main`; offer to rebase it (it would then only add the skill and prompt tweaks) or close it.
- 12 merged remote branches are still on GitHub (deletion is blocked from this sandbox); the user can delete them. Only feature/klein4b-featured-images must stay.
- Profile fill finished: 39 of 40 actors have photos; Tobias Santelmann has none.
- Writer is a single Claude account; with 40 actors it can hit its usage limit.

**Why:** Context for resuming without re-deriving it.

**How to apply:** Start by checking whether these items were finished; the dates are 2026-10-26/27, so they may be stale.
