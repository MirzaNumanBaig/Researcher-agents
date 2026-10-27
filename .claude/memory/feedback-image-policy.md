---
name: feedback-image-policy
description: Image rules for the blog - free models only, AI scene images, never copy publisher photos, never AI images of real people
type: feedback
---

Featured images must come from a free Cloudflare Workers AI model (inside 10,000 free neurons/day), generated from scene prompts with no real people, with AI-generated alt text/caption. Do not reuse publisher/news photos on the site; the collected news image links are research references for training only.

**Why:** Google Publisher Policies do not allow content that infringes copyright, so copying outlet photos risks ad blocking or account suspension; a credit or link-back is not permission. AI images of real celebrities risk misleading readers and right-of-publicity claims.

**How to apply:** Only offer or enable free models (klein 4B, schnell). Recheck model licences (Black Forest Labs terms) before relying on them commercially.
