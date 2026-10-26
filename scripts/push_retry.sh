#!/usr/bin/env bash
# Push the current commit to main, rebasing over pushes that landed meanwhile (bot jobs and people push at the same time,
# and a single "pull --rebase && push" loses the race with "cannot lock ref").
for i in 1 2 3 4 5; do
  git pull -q --rebase -X theirs origin main && git push -q origin HEAD:main && exit 0
  echo "push attempt $i failed, retrying" >&2
  git rebase --abort 2>/dev/null
  sleep $((i * 3))
done
echo "push failed after 5 attempts" >&2
exit 1
