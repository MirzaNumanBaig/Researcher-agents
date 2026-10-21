#!/usr/bin/env bash
# Rebuild the dashboard from the latest main and push it. Run this only after your own changes are pushed:
# it resets the checkout to origin/main. Retries when another workflow pushed at the same moment.
set -euo pipefail
git config user.name "researcher-bot"
git config user.email "researcher-bot@users.noreply.github.com"
for attempt in 1 2 3; do
  git fetch -q origin main
  git reset -q --hard origin/main
  python agents/build_dashboard.py
  git add docs data/articles.json data/stories.json
  [ -f data/writers.json ] && git add data/writers.json
  if git diff --cached --quiet; then echo "dashboard already up to date"; exit 0; fi
  git commit -qm "Update dashboard"
  if git push -q origin HEAD:main; then echo "dashboard pushed"; exit 0; fi
  echo "push raced with another run; retrying ($attempt)"
  sleep $((attempt * 5))
done
echo "::warning::Could not push the dashboard update; the next run will rebuild it."
