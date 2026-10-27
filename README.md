# Researcher-agents
News-gathering agents for **Australia**: collect news about chosen Australian celebrities every 3 hours and publish a leads dashboard.

- `config.json` – the country, the celebrities to track (`celebrities`), the country's Google News edition (`google_news`) and local entertainment feeds (`general_feeds`)
- `agents/collect_news.py` – searches Google News (en-AU edition) for each celebrity and scans the local feeds for mentions; writes `data/leads.json`
- `agents/build_dashboard.py` – renders `docs/index.html`, grouped by celebrity
- `.github/workflows/collect.yml` – runs both every 3 hours and commits the result
- `scripts/setup.sh` – installs [Agent Reach](https://github.com/Panniantong/Agent-Reach) for agents that need wider web access (X, Reddit, YouTube, search)

## Change who is tracked
Edit `celebrities` in `config.json`. Removed names disappear from the next run.

## Change the country
Edit `country`, the `google_news` locale (`hl`, `gl`, `ceid`, e.g. `de` / `DE` / `DE:de` for Germany) and `general_feeds`.

Enable the dashboard: repo Settings → Pages → deploy from branch, folder `/docs`.

## Article → Image pipeline (featured images)

`agents/imagegen/` turns each article into an original FLUX.1 schnell picture: **analyze** the story (story type, event, emotion, setting, props, light, palette, sensitivity) → apply the **visual rules** → write a 60-120 word **prompt** → **generate** → **quality-check** (retry with a new seed, up to 2 times) → attach to WordPress with alt text and a caption. It runs automatically inside `generate_images.py`; if anything fails there the old one-line `image_prompt` path is used, so publishing never stops.

**Run it by hand** (needs `CF_ACCOUNT_ID` and `CF_API_TOKEN`; WordPress modes also `WP_URL`, `WP_USER`, `WP_APP_PASSWORD`):

```
scripts/generate-image --post-id 123              # one WordPress post -> featured image
scripts/generate-image --batch --limit 20         # every post without a featured image
scripts/generate-image --article articles/x.md --out out/   # a repo article, no WordPress
scripts/generate-image --demo --out demo-out      # three fictional sample stories, never publishes
scripts/generate-image --post-id 123 --dry-run --preset glossy_magazine --seed 42
```

Every setting is listed in `.env.example` (environment variable `IMG_*`, or `config.json` → `image_pipeline`). Per article it saves `articles/image-meta/<article>.json` (article id, story type, analysis, final prompt, seed, model, preset, timestamp, quality result per attempt) and keeps the last 20 prompts in `articles/image-meta/_history.json`, so neighbouring images use different shots, angles and palettes.

**Rules enforced in code** (`concept.py`, not just asked of the model): no real name or likeness in a prompt or alt text; no readable text, signs or logos; no children; no weighting syntax or negative prompts; sensitive and high-risk stories (death, health, legal, abuse, rumours) get a calm symbolic scene with no people; the prompt always ends with "No text, no logos, no watermark."

**Style presets** (`--preset`, `IMG_PRESET`): `candid_news_photo` (default), `glossy_magazine`, `cinematic_still`, `soft_illustration`. Add one by adding an entry to `PRESETS` in `agents/imagegen/presets.py` (a label and one style sentence).

**Add a story type:** add its name to `STORY_TYPES` and a row to `DEFAULTS` (emotion, setting, three props, light, palette) in `analyzer.py`, optionally a keyword rule in `TYPE_WORDS`, and a scene sentence in `SCENES` in `prompt_writer.py` (for sensitive types also an entry in `SYMBOLIC` in `concept.py`). `tests/test_imagegen.py` checks every story type automatically.

**LLM provider:** `IMG_LLM_PROVIDER=cloudflare` (default, same secrets as the image model), `anthropic` (needs `ANTHROPIC_API_KEY`), or `none` (keyword analysis and template prompts). The vision quality check needs Meta's licence accepted once on your Cloudflare account (`scripts/generate-image --accept-vision-license`, run only by you); until then it is skipped and only the pixel checks run.
