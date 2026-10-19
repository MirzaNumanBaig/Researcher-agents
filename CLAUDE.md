# Researcher-agents (Modus Carry, Australia)

Everything lives in this repo, so any Claude account/session can continue the work.

- `config.json`: celebrities, country, `interval_hours`, `paused`, per-celebrity `profiles` (photo + social links).
- `agents/collect_news.py`: Google News + Australian feeds -> `data/leads.json` (each new lead gets a `batch` = the run's hour).
- `agents/gate.py`: hourly workflow wake-up; collects only when `interval_hours` passed since `data/usage.json:last_run`.
- `agents/build_dashboard.py`: groups duplicate headlines into stories, renders `docs/index.html` (GitHub Pages, noindex).
- `agents/fetch_profiles.py`: fills empty profile fields from Wikidata/Commons (never overwrites hand edits).
- `.github/workflows/collect.yml`: runs the above and commits `data/` and `docs/`.

To change the dashboard: edit `agents/build_dashboard.py`, run it, commit, push to `main`.
Never commit secrets. WordPress/GitHub tokens belong in GitHub Actions secrets.
