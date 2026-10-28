"""generate-image: python -m imagegen (run with PYTHONPATH=agents, or use scripts/generate-image).

  --post-id 123          one WordPress post: analyze, generate, check, set as featured image
  --batch [--limit N]    every post that has no featured image
  --article articles/x.md   a repo article file (writes the picture next to the meta file, no WordPress)
  --demo                 the three fictional sample stories, never publishes
  --dry-run              do everything except the WordPress upload
  --accept-vision-license   one-time: accept Meta's licence for the vision model on your Cloudflare account (only when YOU run it)
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

from . import config, meta, pipeline, presets, publisher
from . import llm as llmmod

SAMPLES = Path(__file__).resolve().parent / "samples"


def _save_outputs(out, name, res):
    d = Path(out) / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "analysis.json").write_text(json.dumps(res["analysis"], indent=2, ensure_ascii=False) + "\n")
    (d / "prompt.txt").write_text(res["prompt"] + "\n")
    (d / "result.json").write_text(json.dumps({k: res[k] for k in ("ok", "alt", "caption", "seed", "model", "preset", "prompt_source", "attempts", "error", "variation")},
                                              indent=2, ensure_ascii=False) + "\n")
    if res["webp"]:
        (d / "image.webp").write_bytes(res["webp"])
    return d


def _summary(name, res):
    a = res["analysis"]
    print(f"\n=== {name} ===\nANALYSIS ({a['source']}):\n{json.dumps(a, indent=2, ensure_ascii=False)}\nPROMPT ({res['prompt_source']}, "
          f"{len(res['prompt'].split())} words):\n{res['prompt']}\nALT: {res['alt']}\nRESULT: ok={res['ok']} seed={res['seed']} "
          f"attempts={json.dumps(res['attempts'], ensure_ascii=False)} {('error=' + res['error']) if res['error'] else ''}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="generate-image", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--post-id", type=int)
    g.add_argument("--batch", action="store_true")
    g.add_argument("--article")
    g.add_argument("--demo", action="store_true")
    g.add_argument("--accept-vision-license", action="store_true")
    g.add_argument("--list-presets", action="store_true")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--preset", help="candid_news_photo | glossy_magazine | cinematic_still | soft_illustration")
    p.add_argument("--seed")
    p.add_argument("--out", help="folder for analysis.json, prompt.txt, image.webp, result.json")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-caption", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    if a.no_caption:
        os.environ["IMG_CAPTION"] = "off"

    if a.list_presets:
        for k, v in presets.PRESETS.items():
            print(f"{k}: {v['label']}")
        return 0
    if a.accept_vision_license:
        try:
            llmmod.Cloudflare().accept_vision_license()
        except llmmod.LLMError as e:
            print(f"licence step failed: {e}")
            return 1
        print("Vision model licence accepted for this Cloudflare account.")
        return 0

    failed = 0
    if a.demo:
        out = a.out or "demo-out"
        os.environ.setdefault("IMG_META_DIR", str(Path(out).resolve() / "meta"))  # the demo never touches the real prompt history
        for f in sorted(SAMPLES.glob("*.json")):
            res = pipeline.run({**json.loads(f.read_text()), "key": f.stem}, a.preset, a.seed)
            _summary(f.stem, res)
            _save_outputs(out, f.stem, res)
            failed += not res["ok"]
        return 1 if failed else 0

    if a.article:
        import generate_images as gi
        path = Path(a.article)
        front, body = gi.split(path.read_text())
        jobs = [(path.stem, pipeline.article_from_front(front, body, path.stem, gi.field), None)]
    elif a.post_id:
        post = publisher.fetch_post(a.post_id)
        jobs = [(f"post-{post['id']}", {"key": f"post-{post['id']}", "headline": post["title"], "body": post["body"], "category": post["category"],
                                         "source_url": post["source_url"], "names": []}, post["id"])]
    else:
        jobs = []
        for pid in publisher.posts_without_image(a.limit):
            post = publisher.fetch_post(pid)
            jobs.append((f"post-{pid}", {"key": f"post-{pid}", "headline": post["title"], "body": post["body"], "category": post["category"],
                                         "source_url": post["source_url"], "names": []}, pid))
    for name, article, post_id in jobs:
        res = pipeline.run(article, a.preset, a.seed)
        _summary(name, res)
        if a.out:
            _save_outputs(a.out, name, res)
        if res["ok"] and post_id and not a.dry_run:
            media_id, url = publisher.attach(post_id, res["webp"], f"{name}.webp", res["alt"], res["caption"])
            print(f"attached media {media_id} to post {post_id}: {url}")
        failed += not res["ok"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
