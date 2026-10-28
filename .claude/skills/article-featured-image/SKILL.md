---
name: article-featured-image
description: How the featured image for an article is imagined and prompted for Cloudflare FLUX.1 schnell: scene blueprint, fictional stand-in cast, the 10-part prompt order, face and body-language rules, and the quality check. Use when writing or reviewing `image_prompt`, an image prompt, or the image pipeline.
---

# Article featured image (FLUX.1 schnell, v2)

The pipeline in `agents/imagegen/` makes one original picture per article. This skill is the house method behind it. The code enforces the hard rules; this file explains the method so a writer, a reviewer or another AI tool can follow it by hand.

## The flow

1. **Analyze the story**: type, core event, emotion, setting, key objects, light, palette, sensitivity.
2. **Scene blueprint**: shot size, camera, composition, depth layers, and for at most TWO people a body-language card (see below). Built from the news photo when one is allowed and a vision model is available, otherwise from the story.
3. **Stand-in cast**: people in a picture are ORIGINAL fictional characters from `agents/imagegen/cast.json`, matched on gender presentation, age range and clothing style. Same composition and emotion as the reference, new people.
4. **Prompt** in the order below.
5. **Generate** at 1536x864, upscale 2x, crop to 1600x900, light sharpen and tiny grain.
6. **Score 1-5** on six points; any score under 4 gets a new seed (3 attempts), then a calm symbolic scene instead of a face-led picture.

## Hard rules (the code enforces these)

1. Never write a real person's name, nickname or "looks like X" in an image prompt. Never try to reproduce a real person's face or likeness, and never describe identity features of a reference photo's subjects (face shape, nose, eye colour, freckles).
2. Do not recreate an existing photo, film still, album cover, poster, logo or signage. Take the composition, mood and colour logic only.
3. No readable text anywhere in the image.
4. No children. At most 2 people.
5. Sensitive or high-risk stories (death, illness, legal, abuse, minors, unverified rumours): a calm, respectful, symbolic scene (an empty chair, candles, a quiet window, a gavel in soft light) or a back-turned composition. Nothing that implies guilt or a specific event as fact.
6. Build every scene from the article's own facts. If a detail is not in the sources, leave it out.

## The body-language card (one per person)

Write plain visual facts, never identity:

- **facial_expression**: eyebrows, eyes, mouth, jaw. Use muscle cues, not a feeling word. "Inner corners of the brows raised, eyes glassy, lips pressed together, slight jaw tension", not "sad".
- **gaze**: camera, off-frame left or right, down, at the other person.
- **head**: tilt and turn.
- **posture**: shoulders, spine, weight shift.
- **hands**: exact position and what they hold. Keep it simple: holding an object, resting on a surface, in a pocket. Never fingers spread or interlaced in the foreground.
- **interaction** (two people): distance, touch, mirrored or opposing poses.
- **clothing**: type, colour, fabric. Generic, no brand logos.

## Prompt: 90-150 words (never over about 190), no negatives, no weighting

One flowing natural-language prompt, in this order:

1. Shot size and subject: "A medium shot of a woman in her early 30s with ..."
2. Face and expression in detail: eyebrows, eyes, mouth, jaw, gaze.
3. Body language: head tilt, shoulders, posture, hand position, distance or touch between people.
4. Clothing and props.
5. Setting and depth: foreground, midground, background blur.
6. Camera: lens, angle, shallow depth of field.
7. Lighting: a named source and its direction, soft or hard.
8. Mood and colour palette (name real colours, never "colourful").
9. Realism tail: "natural skin texture with visible pores and small imperfections, candid unposed moment, shot on a full-frame camera, fine film grain, true-to-life colour".
10. End with: "No text, no logos, no watermark."

Rules for faces with schnell:

- Medium or medium-wide shots. No extreme close-ups. No more than 2 faces.
- Describe emotion through specific muscle cues.
- No hype words (masterpiece, ultra-detailed, 8k).
- Vary camera angle, setting and palette between articles; the pipeline keeps the last 20 prompts and the last stand-ins used to do this.
- schnell has no negative prompt: say what IS in the frame ("an empty stage, bare brick wall"), not what is not. The closing "No text, no logos, no watermark." sentence is the one deliberate exception.
- Keep the subject in the middle band: the 5:3 crop removes the top and bottom of the raw image.

### Example (two people, relationship story)

"A medium-wide shot of a woman in her late 20s with long straight black hair and warm beige skin and a man in his late 40s with thinning dark hair and round glasses, seated close at a small table, mirrored relaxed poses. The woman's brows softened, eyes warm and a little crinkled, a small closed-lip smile, jaw loose, gaze on the other person; head tilted toward them, shoulders dropped, one hand resting on the table edge. The man's brows lifted, eyes bright and crinkled, a wide natural smile, jaw relaxed, gaze on the other person; head tipped back mid-laugh, one hand in a coat pocket. The woman wears a camel trench coat; the man wears a brown suede jacket. The setting is a quiet restaurant terrace, string lights soft behind. 50mm lens, eye-level, shallow depth of field. Lit by warm string lights from above and behind. Tender mood, warm amber and soft rose palette. Natural skin texture with visible pores and small imperfections, candid unposed moment, shot on a full-frame camera, fine film grain, true-to-life colour. No text, no logos, no watermark."

## What the writer puts in `image_prompt` (front matter)

Keep it a short, safe scene only: one English sentence under 25 words, no people, no names, no text. The pipeline builds the full prompt above from the story; `image_prompt` is only the fallback used when the pipeline cannot run, and that path sends it as written.

## The quality check

A vision model scores 1-5: face naturalness, expression matches the blueprint, hands and body anatomy, composition match, realism, no text or logos. Reject and retry with a new seed if ANY score is under 4. A recognisable real person, nudity or graphic injury also rejects. If three face-led attempts fail, make a symbolic scene (props, setting, silhouette) instead.

## Checking output by hand

Run the manual workflow **Image pipeline demo** (three fictional stories) or **Test image model** (one scene), then look at the artifact. Locally: `scripts/generate-image --demo --out demo-out`. Judge each picture against the six points above; change one thing at a time (simplify the scene, drop a prop, change the angle) and retry.

## Not an editorial photo

These are illustrations made for a story. The AI flag is kept in `articles/image-meta/<article>.json` (and a visible caption can be switched on with `IMG_CAPTION`); do not describe a picture as a photo of the real people or the real event in alt text or copy.
