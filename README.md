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

## Usage in the dashboard

The dashboard's **Usage** tab shows two things:

- **Picture generation (Cloudflare neurons):** today's estimated neurons per account against the 9,000 budget and the 10,000 free limit, picture attempts today, and the last 14 days. Source: `articles/image-meta/_usage.json`. These are estimates from the calls we send, not Cloudflare's own meter.
- **Article writing (Claude tokens):** input, output and cached tokens, turns and the API-equivalent cost for today, 7 days and 30 days, per writer account, and the latest writer runs. Source: `data/claude_usage.json`, filled by `agents/record_usage.py`, which `write-articles.yml` runs after each article from the `execution_file` output of `anthropics/claude-code-action`. Tokens are exact; a Claude plan is not billed per token, so the dollar figure is only what the same work would cost on the API. Codex runs are not counted (no usage data).

## Article → Image pipeline (featured images)

`agents/imagegen/` turns each article into an original FLUX.1 schnell picture:

1. **Analyze** the story (story type, event, emotion, setting, props, light, palette, sensitivity).
2. **Scene blueprint** (`blueprint.py`): shot size, camera, composition, depth layers, and for at most two people a body-language card (eyebrows, eyes, mouth, jaw, gaze, head, posture, hands, interaction, clothing). With `IMG_REFERENCE_IMAGES=true` and a news photo, a vision model fills it in from the photo (visual facts only, never who the people are). Otherwise it is built from the story. Sensitive stories get no people.
3. **Stand-in cast** (`cast.py`, `cast.json`): every person in a picture is one of 12 fictional characters, matched by gender presentation, age range and clothing and rotated so the site shows varied people. A prompt never contains a real name or "looks like".
4. **Prompt** (90-150 words, up to about 190 for two people): shot size and subject, face, body language, clothing and props, setting and depth, camera, light, mood and palette, realism tail, "No text, no logos, no watermark."
5. **Generate** at 1536x864, **upscale** 2x (Lanczos, or Real-ESRGAN when installed), crop to **1600x900** (1920x1080 by setting), light sharpening and tiny grain, WebP or JPEG under 400 KB where possible (`finish.py`).
6. **Score** with a vision model (1-5: face naturalness, expression match, hands and anatomy, composition match, realism, no text or logos). Any score under 4 means a new seed, up to 3 attempts; if all fail, one calm symbolic scene (props, setting, no faces) is made instead. Nothing is used if that fails too.
7. **WordPress**: featured image with a factual one-sentence alt text. **No visible caption or credit is added** (set `IMG_CAPTION` to a text to turn one on). The AI flag, prompt, seed, model, blueprint, stand-in ids and scores are kept in `articles/image-meta/<article>.json`.

It runs automatically inside `generate_images.py`; if anything fails there the old one-line `image_prompt` path is used, so publishing never stops.

**Run it by hand** (needs `CF_ACCOUNT_ID` and `CF_API_TOKEN`; WordPress modes also `WP_URL`, `WP_USER`, `WP_APP_PASSWORD`):

```
scripts/generate-image --post-id 123              # one WordPress post -> featured image
scripts/generate-image --batch --limit 20         # every post without a featured image
scripts/generate-image --article articles/x.md --out out/   # a repo article, no WordPress
scripts/generate-image --demo --out demo-out      # three fictional sample stories, never publishes
scripts/generate-image --post-id 123 --dry-run --preset glossy_magazine --seed 42
```

Every setting is in `.env.example` (environment variable `IMG_*`, or `config.json` -> `image_pipeline`): sizes, steps, upscaler, output size and format, quality and file-size target, sharpening and grain, minimum score, caption, cast file. The history of the last 20 prompts (`_history.json`) makes neighbouring images use different shots, angles, palettes and stand-ins.

**Model:** FLUX.2 klein 4B (`@cf/black-forest-labs/flux-2-klein-4b`) is the default; FLUX.1 schnell stays available (`IMG_IMAGE_MODEL`). Klein is asked for 1024x576 (multipart request, no steps) and upscaled 2x; schnell for 1536x864. If Cloudflare's safety filter flags a picture, a new seed is tried like any other rejected attempt.

**Daily budget per account:** each call adds an estimate of its neurons (klein picture 150, schnell 170, text 20, vision 80) to `articles/image-meta/_usage.json`, kept per account slot (1 = `CF_ACCOUNT_ID`, 2 = `CF_ACCOUNT_ID_2` ...), never the account id, with 30 days of history. At `IMG_NEURON_BUDGET` (default 9,000 of the 10,000 free neurons) the next account takes over; Cloudflare's own limit is still the safety net. When every account is at its budget the run stops with a clear message. The numbers are estimates, so keep the margin.

**More than one Cloudflare account:** add `CF_ACCOUNT_ID_2` + `CF_API_TOKEN_2` (and `_3`, `_4`) as GitHub secrets. The first account is used until Cloudflare says its free neurons are used up; the next one then takes over at once, for images, text and vision alike. The daily cap grows with the number of accounts. Only complete pairs count. Check Cloudflare's terms before opening extra free accounts; paying as you go on one account is the other way to get more.

**Cost guard:** Cloudflare's free allowance is 10,000 neurons a day, and an image attempt costs roughly 170 of them plus the text and vision calls, so `IMG_DAILY_IMAGE_CAP` (default 40 attempts per UTC day, counted in `articles/image-meta/_usage.json`) stops the run before the allowance is spent. A "daily allocation used up" error is never retried.

**Rules enforced in code** (`concept.py`, not just asked of the model): no real name or likeness in a prompt or alt text; no readable text, signs or logos; no children; no weighting syntax or negative prompts; at most two people; sensitive and high-risk stories (death, health, legal, abuse, rumours) get a calm symbolic scene with no people; the prompt always ends with "No text, no logos, no watermark."

**Style presets** (`--preset`, `IMG_PRESET`): `candid_news_photo` (default), `glossy_magazine`, `cinematic_still`, `soft_illustration`. Add one by adding an entry to `PRESETS` in `agents/imagegen/presets.py` (a label, a style sentence and a realism `tail`).

**Add a story type:** add its name to `STORY_TYPES` and a row to `DEFAULTS` (emotion, setting, three props, light, palette) in `analyzer.py`, optionally a keyword rule in `TYPE_WORDS`, a scene sentence in `SCENES` in `prompt_writer.py` (for sensitive types also an entry in `SYMBOLIC` in `concept.py`), and, if it should show people, a row in `PLAN` in `blueprint.py` (number of people, how they stand, clothing hint). `tests/test_imagegen.py` checks every story type automatically.

**Add or edit a stand-in:** edit `agents/imagegen/cast.json` (id, gender presentation, age, hair, build, skin, three clothing styles). Keep them fictional, 8-12 cards.

**Real-ESRGAN:** set `IMG_UPSCALER=realesrgan` on a machine that has the `realesrgan-ncnn-vulkan` program (or change `IMG_UPSCALE_CMD`); if it is missing or fails, Lanczos is used. GitHub's standard runners have no GPU, so the default stays Lanczos. Face restoration (CodeFormer / GFPGAN) is off; `IMG_FACE_RESTORE=command` runs `IMG_FACE_RESTORE_CMD` on accepted images.

**LLM provider:** `IMG_LLM_PROVIDER=cloudflare` (default, same secrets as the image model), `anthropic` (needs `ANTHROPIC_API_KEY`), or `none` (keyword analysis and template prompts). The vision steps (blueprint from a photo, scored check) need Meta's licence accepted once on your Cloudflare account (`scripts/generate-image --accept-vision-license`, run only by you); until then the scored check is skipped and only the pixel checks run.

