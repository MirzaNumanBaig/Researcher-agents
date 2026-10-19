# Researcher-agents
News-gathering agents: collect celebrity news every 3 hours and publish a leads dashboard.

- `agents/collect_news.py` – pulls RSS feeds listed in `config.json` into `data/leads.json`
- `agents/build_dashboard.py` – renders `docs/index.html`
- `.github/workflows/collect.yml` – runs both every 3 hours and commits the result
- `scripts/setup.sh` – installs [Agent Reach](https://github.com/Panniantong/Agent-Reach) for agents that need wider web access (X, Reddit, YouTube, search)

Enable the dashboard: repo Settings → Pages → deploy from branch, folder `/docs`.
Edit `config.json` to change feeds or filter by `keywords`.
