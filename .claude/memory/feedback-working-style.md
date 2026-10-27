---
name: feedback-working-style
description: How this operator wants work delivered - branch, test, ask before merging to main, report honestly
type: feedback
---

Make each change on a branch, test it (unit tests plus a real browser or mock-server run where possible), push, then ask whether to merge to `main`. The operator answers "yes" / "merge it". Merge only after that, with checks: fetch main, rebase, run all tests, then push HEAD:main. Never touch a branch with an open PR unasked (PR #5).

**Why:** They approved merges one at a time, and several fixes touched the live pipeline that sends posts to a monetised site.

**How to apply:** Do not merge unprompted. After merging, say what was and was not verified. Correct earlier mistakes openly (e.g. a wrong "pending for an hour" claim was corrected). They get impatient when asked the same question repeatedly, so ask once, clearly.
