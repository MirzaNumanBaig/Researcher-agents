# Researcher-agents (Modus Carry, Australia)

Everything lives in this repo, so any AI account or tool (Claude, ChatGPT/Codex, others) can continue the work. This file is the single source of truth; CLAUDE.md imports it.

- `config.json`: celebrities, country, `interval_hours`, `paused`, per-celebrity `profiles` (photo + social links).
- `agents/collect_news.py`: Google News + Australian feeds -> `data/leads.json` (each new lead gets a `batch` = the run's hour).
  Quality filters in `config.json`: `headline_must_name` (the headline must name the celebrity), `exclude_sources` (outlets to drop), `max_age_hours` (new stories older than this are ignored, default 48). Direct publisher feeds in `general_feeds` need no Google redirect.
- `agents/fetch_sources.py`: downloads the pages behind a brief; writes `Readable sources: n of m` at the top of `work/.../sources.md` and a loud warning when nothing is readable (the writer then skips instead of guessing).
- `agents/gate.py`: hourly workflow wake-up; collects only when `interval_hours` passed since `data/usage.json:last_run`.
- `agents/build_dashboard.py`: groups duplicate headlines into stories, renders `agents/dashboard_template.html` into `docs/index.html` (GitHub Pages, noindex).
- `agents/fetch_profiles.py`: fills empty profile fields from Wikidata/Commons (never overwrites hand edits).
- `.github/workflows/collect.yml`: runs the above and commits `data/` and `docs/`.

To change the dashboard: edit `agents/dashboard_template.html` (layout, styles, Setup window) or `agents/build_dashboard.py` (data), run the builder, commit, push to `main`.
Never commit secrets. WordPress/GitHub tokens belong in GitHub Actions secrets.
- `mcp/server.py`: stdio MCP server (stdlib only) so any Claude account can read stories and control the system via the GitHub API. Setup: `mcp/README.md`.
- `articles/`: drafts written by Claude (`status: pending|approved|rejected` in the front matter). Only approved drafts are ever published.
- `agents/publish_wordpress.py` + `.github/workflows/publish-wordpress.yml`: sends `status: approved` drafts to WordPress with their `wp_status` (draft/pending/publish).

## How to operate this system (for any Claude account with GitHub access)
- Settings: edit `config.json` (`celebrities`, `interval_hours` 1-24, `paused` true/false, `profiles`). A change to it triggers a refresh.
- Run now: start the `collect.yml` workflow (workflow_dispatch).
- News: `data/stories.json` = grouped stories (outlets + links), `batch` = the run they were found in.
- Briefs: every run writes `briefs/<batch>/<celebrity>.json` (that run's stories for one celebrity, with all outlet links). One article per brief.
- Write articles: open the source links, read the full pages, cross-check facts, write ORIGINAL text (never copy). Save as
  `articles/<batch-slug>-<celebrity-slug>.md` (e.g. `2026-10-20-16-00-nicole-kidman.md`) with front matter: `title`, `status: pending`, `wp_status: draft|pending|publish`,
  `batch` (exact label, e.g. "2026-10-20 16:00"), `celebrity` (exact name), `sources` (list of URLs). The dashboard matches drafts to batches by `batch` + `celebrity`.
- "Write all pending articles": for each brief without a matching draft, in the latest batches, write one. Skip briefs with only junk (ads, old news).
- Approval: only a human approves. Setting `status: approved` makes GitHub send it to WordPress; `wp_status` decides how it appears. Never approve on your own.

## Automatic pipeline
`collect.yml` (every `interval_hours`) -> `make_briefs.py` -> `write-articles.yml` (runs after collect): `fetch_wp_site.py` saves the site's
categories/tags/recent posts to `data/wp_site.json`; `pending_briefs.py` lists briefs without an article; one Claude job per brief
(max-parallel 1) follows `prompts/article.md` and writes `articles/<batch>-<celebrity>.md`; then `publish_wordpress.py --auto-approve`
sends new drafts to WordPress with `config.json:wp_default_status` (default `pending` = review in WordPress). `auto_send: false` stops auto-sending
(drafts then wait for a human `status: approved`). Needs secrets: `CLAUDE_CODE_OAUTH_TOKEN`, `WP_URL`, `WP_USER`, `WP_APP_PASSWORD`.
Inside that workflow you only write the one article you are given; never set `status: approved`.

## Provider independence (who writes the articles is swappable)
The repo is the hub: `briefs/` (input) -> any AI worker following `prompts/article.md` -> `articles/` (output) -> GitHub sends to WordPress.
`write-articles.yml` tries writers in order until one produces the article file: Claude account 1 (`CLAUDE_CODE_OAUTH_TOKEN`), account 2
(`..._2`), account 3 (`..._3`), then OpenAI Codex (`OPENAI_API_KEY`). A writer whose secret is missing is skipped; one that fails or hits its
usage limit hands over to the next. `agents/fetch_sources.py` downloads the source pages first, so a writer needs no web access.
To change writer: add/replace/remove those secrets. To use a different tool by hand: give it `prompts/article.md`, one brief and its sources file,
and ask it to save the article at the stated path. Interactive sessions (any MCP-connected AI) can do the same for briefs with no article.
