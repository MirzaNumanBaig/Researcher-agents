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
