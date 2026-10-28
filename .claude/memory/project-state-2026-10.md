---
name: project-state-2026-10
description: State of Researcher-agents as of 2026-10-28 - what shipped (image pipeline v2, klein 4B, two Cloudflare accounts, Usage tab), what is pending, what the user must do
type: project
---

**Shipped and on `main`** (all via branches then merge): publish fix (WordPress 400 from reading only 100 tags), publish fallback + failure-alert issue + tests, per-article image links, better source reading (cookie walls, JSON-LD, up to 5 outlets), dashboard Last-48-hours / Archive tabs with article-state chips and Articles status tabs with featured images (`wp_image`), 30-day cleanup (`keep_days: 30`, `dashboard_hours: 48`), push retry script, wrapped actor picker with search (PR #6), 40 tracked actors (surnames Fox/Oh/Short/Williams/Anderson need full-name match), image generation only for approved / just-sent articles, `test-image-model.yml` (optional size, 4:5 output, `style: none`), memory in the repo.

**PR #9 merged to `main` 2026-10-28 (commit dbb3342)** = the whole Article -> Image pipeline + v2:
- `agents/imagegen/`: analyzer, scene blueprint (`blueprint.py`), 12 fictional stand-ins (`cast.json`, `cast.py`), concept rules, prompt writer (90-150 words, up to ~190 for two people), generator, finishing (`finish.py`), scored vision checker (1-5, reject under 4, 3 attempts, then a symbolic scene), publisher, CLI `scripts/generate-image`. The old one-line `image_prompt` path in `generate_images.py` is the fallback when the pipeline fails.
- Output: generate (klein 1024x576 / schnell 1536x864), upscale 2x (Lanczos default; Real-ESRGAN opt-in `IMG_UPSCALER=realesrgan`), crop **1600x900**, light sharpen + grain, WebP/JPEG under 400 KB where possible.
- **No visible AI caption/credit** (`IMG_CAPTION` empty by default, user decision 2026-10-28); the AI flag, prompt, seed, blueprint, stand-in ids and scores live in `articles/image-meta/<article>.json`. Alt text is one factual sentence.
- **Default model FLUX.2 klein 4B** (user decision; schnell stays selectable via `IMG_IMAGE_MODEL`). The user finds schnell skin plastic with an "alien" look; klein faces were clearly more natural (pores, freckles).
- **Several Cloudflare accounts** (`agents/cf_accounts.py`): secrets `CF_ACCOUNT_ID`/`CF_API_TOKEN`, then `_2`... (workflows pass `_2`-`_4`); estimated neurons per account slot per UTC day in `articles/image-meta/_usage.json` (+30 days history); the next account takes over at `IMG_NEURON_BUDGET` (9000, user decision), Cloudflare's 429 is the backup. The second account was verified with a real test run.
- **Dashboard Usage tab + a usage strip right under the header** (two chips: Pictures per account, Claude tokens today; a click opens the tab; rebuilt with the dashboard, `agents/usage_stats.py`): Cloudflare neuron estimates per account + Claude tokens per article (`data/claude_usage.json`, written by `agents/record_usage.py` from the `execution_file` output of `anthropics/claude-code-action` in `write-articles.yml`).
- Skill `.claude/skills/article-featured-image/` rewritten for the blueprint / stand-in / 10-part prompt method. CI (`test.yml`) now installs Pillow. 148 tests pass (mock servers only).

**Real data seen 2026-10-28:** the first Claude record landed (`data/claude_usage.json`, Chris Hemsworth article: 1,129 tokens), so the `execution_file` parser works on a real log. Account 1 was stopped by Cloudflare's own limit, so its usage was never counted; accounts stopped that way are now saved as `spent` (slot only) and shown as "limit reached".

**Still NOT proven with real services:** a full pipeline run on klein; the vision steps (need Meta's licence accepted once PER Cloudflare account, only the user can do it); Real-ESRGAN; face restoration; whether the cap/budget estimates (klein 150, schnell 170 neurons per picture) are accurate.

**Klein safety filter:** Cloudflare flagged klein's output (HTTP 400 "Your output has been flagged") for EVERY prompt with a woman in an evening gown (nightclub / red carpet, several colours, necklines, angles; 7 tries), while an office portrait passed. Do not keep rewording prompts to dodge the filter; the pipeline just retries with a new seed, and the symbolic scene is the last resort. The user decided NOT to add a schnell fallback. Schnell rejects prompts over 2048 characters (HTTP 400) and reads only ~256 tokens.

Cloudflare cost facts (price table, 1536x864 = 6 tiles): free 10,000 neurons/day per account, then $0.011 per 1,000; schnell ~130-170 neurons/picture, klein-4b ~104-156; klein-9b ~1,400 ($0.016), flux-2-dev ~4,500+, phoenix ~3,200, lucid-origin ~3,800 per picture. Extra free accounts may breach Cloudflare's terms (user was warned); pay-as-you-go on one account is the alternative.

**Branches:** after PR #9 the only branches that should exist are `main`. 20 old remote branches were verified (content in `main`, replaced by PR #9, or empty) and the user was given the list and the delete command; this sandbox's proxy returns 403 for branch deletion, so the USER deletes them (https://github.com/MirzaNumanBaig/Researcher-agents/branches). PR #5 (klein4b skill) was closed as superseded; its commits stay on the PR page. GitHub auto-deletes a PR's branch when it is merged. Check `git ls-remote --heads origin` before assuming they are gone.

**Pending / open (verify each; they may be done by the time you read this):**
- Run the demo (`image-pipeline-demo.yml`, dispatch on `main`) or watch the next real run and show the user real klein pictures, analysis/blueprint JSON and scores; check the Usage tab fills in.
- Secrets: the user added the second Cloudflare account (`CF_ACCOUNT_ID_2`/`CF_API_TOKEN_2`); a third/fourth need `_3`/`_4`.
- Profile fill finished: 39 of 40 actors have photos; Tobias Santelmann has none.
- Writer accounts: only Claude account 1 exists (dashboard warns "1 writer account"); with 40 actors it can hit its usage limit.

**Why:** Context for resuming without re-deriving it.

**How to apply:** Start by checking whether these items were finished; the dates are 2026-10-26 to 28, so they may be stale.
