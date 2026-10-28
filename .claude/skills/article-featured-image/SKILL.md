---
name: article-featured-image
description: Write the `image_prompt` for an article's AI featured image, tuned for Cloudflare FLUX.1 schnell. Use on every article, when filling the `image_prompt` front matter field.
---

# Article featured image (FLUX.1 schnell)

The pipeline (`agents/generate_images.py`) sends your `image_prompt` to `@cf/black-forest-labs/flux-1-schnell`, appends the `STYLE` suffix, crops the result to 1500x900 and uploads it as the post's featured image. You only write the scene. Everything below is about writing a scene this model draws well.

## Hard rules (house policy)

1. Scenes, objects, places and mood only. NEVER a real person, a name, a face, a celebrity likeness, a brand, a logo or readable text.
2. Build the scene from the article's own facts (film genre, venue, city, season, mood). If a detail is not in the sources, leave it out. Never a random generic scene.
3. For an article about a named person, draw the setting that goes with the story (premiere, stage, set, location, object), with no people in frame or only distant silhouettes.
4. No signs, posters, marquees or banners: the model garbles lettering.

## How FLUX.1 schnell reads a prompt

- It understands natural sentences, not keyword piles. Write one fluent description, subject first.
- There is **no negative prompt**. Words like "no text" can plant the very thing you are avoiding, so describe what IS there ("an empty stage, bare brick wall") instead of what is not.
- Early words weigh most. Put the main subject and setting first, mood and lighting next, style last.
- It runs only 4 steps, so keep it simple: one subject, one place, one light source, one palette. Crowded scenes turn muddy.
- The prompt limit is 2048 characters but the sweet spot is one sentence under 25 words.
- Size cannot be chosen. The model returns a square-ish image and the pipeline centre-crops it to 5:3, losing the top and bottom. Keep the subject in the middle band, horizontally centred, and say "wide panoramic composition" for places.

## Prompt formula

`[subject + setting from the article], [one light source], [one palette or mood], wide panoramic composition`

The pipeline adds the photographic style suffix, so do not repeat "photorealistic", "4k" or "masterpiece".

## Mood to words

| Mood | Words |
|---|---|
| Premiere, awards, luxury | red carpet at night, golden spotlights, deep black and gold |
| Dark, thriller | wet street at night, teal and orange glow, long shadows |
| Romantic | soft pink and gold dusk, gentle haze, candlelight |
| Epic, adventure | warm golden hour, deep blue shadows, vast landscape |
| Music, concert | stage with warm spotlights, haze in the air, magenta and blue light |
| Sport | empty stadium under floodlights, wet grass, high contrast |
| Quiet drama | overcast coast, soft grey-blue light, a single lit window |
| Comedy, light | bright pastel set, soft daylight, warm yellow and sky blue |

Name exact colours and where they sit ("a single amber lamp on a blue wall"). Do not write "colourful".

## Good and bad

- Good: `An empty cinema auditorium with red velvet seats, a bright projector beam cutting through dust, warm amber light, wide panoramic composition`
- Good: `A fog-covered fishing harbour at dusk, one lit window above the water, soft grey-blue light, wide panoramic composition`
- Bad: `Nicole Kidman on the red carpet` (a real person)
- Bad: `A cinema with a sign saying PREMIERE, no people, no text` (lettering plus negations)
- Bad: `Epic, stunning, ultra detailed, 8k masterpiece cinematic movie` (keyword pile, no scene)

## Checklist before you save the field

- One sentence under 25 words, in English, inside double quotes.
- Subject and setting come from this article.
- No person, name, brand, logo, sign or text; no "no ..." phrases.
- Subject sits in the centre of the frame.

## Checking the output

Run the manual workflow **Test image model** (`.github/workflows/test-image-model.yml`) with model `@cf/black-forest-labs/flux-1-schnell` and your scene; download the `sample.webp` from the run. Or locally: `CF_ACCOUNT_ID=... CF_API_TOKEN=... python agents/generate_images.py --sample "<scene>" --out sample.webp`. Reject a picture that shows a recognisable person, readable text, a logo, or a subject lost in the crop; change one thing in the scene and retry.
