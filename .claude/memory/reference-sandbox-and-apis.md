---
name: reference-sandbox-and-apis
description: What this cloud sandbox can and cannot do with GitHub/Cloudflare, and the working workarounds
type: reference
---

Sandbox limits (proxy returns 403): listing Actions secrets/variables, changing repo settings, deleting branches (REST or `git push --delete`), GraphQL (so `gh workflow run` and `gh pr merge` fail). Do not look for workarounds.

What works: dispatch a workflow with `gh api -X POST repos/MirzaNumanBaig/Researcher-agents/actions/workflows/<file>.yml/dispatches -f ref=main -f 'inputs[x]=y'`; merge a PR with `gh api -X PUT repos/.../pulls/<n>/merge -f merge_method=squash`; read run logs with `gh run view <id> --log`; download artifacts with `gh run download`. A shallow clone needs `git fetch --depth=5000 origin main` before ancestry checks are trustworthy. Run tests as `env HOME=/tmp/emptyhome GIT_CONFIG_NOSYSTEM=1 python3 -m unittest discover tests` to mimic CI (no git identity).

Workflow dispatch also works for a workflow that exists only on a feature branch: `-f ref=<branch>` (and a push to a branch can trigger a `push:` workflow filtered to that branch), so no merge is needed to test one with the real secrets.

Cloudflare facts learned by running them: FLUX.1 schnell accepts ONLY `prompt` and `steps` (a `seed`, `width` or `height` returns HTTP 400 "Additional or unevaluated properties"); an image costs roughly 170 neurons, not the ~60 the price table suggests (75 images exhausted the 10,000 free neurons); a spent allowance returns HTTP 429 "used up your daily free allocation" and did not renew at 00:00 UTC when tried at 00:01-00:06; Meta's vision-model licence must be accepted once by the user.

Secrets cannot be listed, but workflow logs prove they exist: the image step printed "CF_ACCOUNT_ID / CF_API_TOKEN not set" on Oct 22 14:22 UTC and "25 image(s) created, 0 failed" from 14:46. Cloudflare Workers AI: free 10,000 neurons/day, then $0.011 per 1,000; model ids `@cf/black-forest-labs/flux-2-klein-4b` (multipart request), `@cf/black-forest-labs/flux-1-schnell` (JSON, no size input), `@cf/lykon/dreamshaper-8-lcm`; Leonardo Lucid/Phoenix cost 3,400-4,100 neurons per image (too expensive for free). Pricing: https://developers.cloudflare.com/workers-ai/platform/pricing/ . AdSense copyright rule: https://support.google.com/publisherpolicies/answer/10502938

**How to apply:** Use these routes first; tell the user what only they can do (secrets, settings, branch deletion).
