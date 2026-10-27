"""Article -> Image pipeline: analyzer JSON parsing, safety rules, prompt quality, generator retries, quality check, end to end (mock servers)."""
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "agents"))
from imagegen import analyzer, checker, concept, config, generator, meta, pipeline, prompt_writer, publisher  # noqa: E402
from imagegen import llm as llmmod  # noqa: E402

NAMES = ["Elena Marlowe", "Tom Hargrove", "Margaret Ellison"]


def png(w=1344, h=768, flat=False):
    from PIL import Image
    if flat:
        img = Image.new("RGB", (w, h), (90, 90, 90))
    else:  # a colourful gradient: passes the blank/dark/bright checks
        g = Image.linear_gradient("L").resize((w, h))
        img = Image.merge("RGB", (g, g.transpose(Image.FLIP_LEFT_RIGHT), g.transpose(Image.ROTATE_180)))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


class FakeLLM:
    def __init__(self, analysis=None, prompts=(), verdicts=()):
        self.analysis, self.prompts, self.verdicts = analysis, list(prompts), list(verdicts)
        self.seen = []

    def complete(self, system, user, max_tokens=700, temperature=0.4):
        self.seen.append(user)
        if "picture editor at an entertainment news site" in system:
            return json.dumps(self.analysis) if self.analysis is not None else "not json at all"
        return self.prompts.pop(0) if self.prompts else "x"

    def vision(self, system, user, image, mime="image/webp"):
        v = self.verdicts.pop(0) if self.verdicts else {}
        if isinstance(v, Exception):
            raise v
        return json.dumps(v)


GOOD_VERDICT = {"visible_text_or_logos": False, "distorted_hands_or_faces": False, "recognizable_real_person": False, "nudity": False,
                "graphic_injury": False, "matches_story_mood": True, "notes": "fine"}


class ParseJson(unittest.TestCase):
    def test_fences_chatter_and_trailing_commas(self):
        self.assertEqual(llmmod.parse_json('Sure!\n```json\n{"a": 1, "b": [1, 2,],}\n```\nHope it helps'), {"a": 1, "b": [1, 2]})

    def test_no_json_raises(self):
        with self.assertRaises(ValueError):
            llmmod.parse_json("sorry, I cannot")


class Analyzer(unittest.TestCase):
    def test_invalid_story_type_and_clipping(self):
        a = analyzer.normalize({"story_type": "gossip", "key_objects": "a, b, c, d, e, f, g", "palette": ["red"], "sensitivity": "weird"}, "Stars dine out")
        self.assertIn(a["story_type"], analyzer.STORY_TYPES)
        self.assertTrue(3 <= len(a["key_objects"]) <= 5)
        self.assertTrue(2 <= len(a["palette"]) <= 3)
        self.assertIn(a["sensitivity"], analyzer.SENSITIVITY)

    def test_sensitivity_can_only_go_up(self):
        self.assertEqual(analyzer.normalize({"story_type": "other", "sensitivity": "safe"}, "Actor dies aged 84")["sensitivity"], "high_risk")
        self.assertEqual(analyzer.normalize({"story_type": "legal", "sensitivity": "high_risk"}, "Star seen at cafe")["sensitivity"], "high_risk")
        self.assertEqual(analyzer.normalize({}, "Court hears claim")["sensitivity"], "sensitive")

    def test_unusable_llm_answer_falls_back_to_rules(self):
        a = analyzer.analyze("Couple marry on a clifftop", "", "", llm=FakeLLM(analysis=None))
        self.assertEqual((a["story_type"], a["source"]), ("wedding", "rules"))

    def test_good_llm_answer_is_used(self):
        raw = {"story_type": "film_release", "core_event": "A film gets a date.", "emotion": "anticipatory", "setting": "film set", "key_objects": ["a clapperboard", "a reel", "a lens"],
               "time_and_light": "a bright projector beam", "palette": ["deep blue", "gold"], "sensitivity": "safe"}
        a = analyzer.analyze("Film date", "", "", llm=FakeLLM(analysis=raw))
        self.assertEqual((a["story_type"], a["source"], a["setting"]), ("film_release", "llm", "film set"))


class SafetyRules(unittest.TestCase):
    def test_strip_names_full_surname_and_shared_words(self):
        clean, removed = concept.strip_names("Elena Marlowe and later Hargrove stand together", NAMES)
        self.assertNotIn("Marlowe", clean)
        self.assertNotIn("Hargrove", clean)
        self.assertIn("an anonymous figure", clean)
        self.assertEqual(concept.strip_names("A short walk past a fox", ["Martin Short", "Michael J. Fox"])[0], "A short walk past a fox")  # common words survive

    def test_sanitize_removes_syntax_likeness_and_text_requests(self):
        dirty = ("A (woman:1.3) who looks like Elena Marlowe holds a sign reading HELLO, in the style of a famous painter. "
                 "Negative prompt: blurry. A poster and a billboard behind. No text, no logos.")
        s = concept.sanitize_prompt(dirty, NAMES)
        for bad in ("Marlowe", "looks like", ":1.3", "Negative", "HELLO", "poster", "billboard", "style of"):
            self.assertNotIn(bad, s)
        self.assertTrue(s.endswith(concept.FINAL_SENTENCE))
        self.assertEqual(s.count("No text"), 1)

    def test_check_prompt_flags_names_children_people_and_length(self):
        base = " ".join(["quiet"] * 60) + ". " + concept.FINAL_SENTENCE
        self.assertEqual(concept.check_prompt(base, NAMES), [])
        self.assertTrue(any("name" in p for p in concept.check_prompt(base + " Marlowe", NAMES)))
        self.assertTrue(any("child" in p for p in concept.check_prompt("A child " + base, NAMES)))
        self.assertTrue(any("sensitive" in p for p in concept.check_prompt("A woman " + base, NAMES, "sensitive")))
        self.assertTrue(any("words" in p for p in concept.check_prompt("short. " + concept.FINAL_SENTENCE, NAMES)))
        self.assertTrue(any("no-text" in p for p in concept.check_prompt(base[:-5], NAMES)))

    def test_word_cap(self):
        long = " ".join(f"Sentence number {i} is here." for i in range(60))
        self.assertLessEqual(concept.words(concept.sanitize_prompt(long, NAMES)), concept.MAX_WORDS)


class PromptWriter(unittest.TestCase):
    def analysis(self, kind, sens="safe"):
        a = dict(analyzer.heuristic("headline"), story_type=kind, sensitivity=sens)
        emo, setting, objs, light, pal = analyzer.DEFAULTS[kind]
        a.update(emotion=emo, setting=setting, key_objects=list(objs), time_and_light=light, palette=list(pal))
        return a

    def test_template_prompt_is_valid_for_every_story_type_and_sensitivity(self):
        for kind in analyzer.STORY_TYPES:
            for sens in analyzer.SENSITIVITY:
                a = self.analysis(kind, sens)
                p = prompt_writer.write_prompt(a, "candid_news_photo", [], NAMES, None, kind)["prompt"]
                self.assertEqual(concept.check_prompt(p, NAMES, sens if concept.is_sensitive(a) else "safe"), [], (kind, sens, p))
                self.assertTrue(60 <= concept.words(p) <= 120, (kind, concept.words(p)))

    def test_prompt_follows_the_order_and_names_a_light_source(self):
        p = prompt_writer.write_prompt(self.analysis("breakup"), "candid_news_photo", [], NAMES, None, "k")["prompt"]
        self.assertLess(p.index("lens"), p.index("Lit by"))
        self.assertLess(p.index("Lit by"), p.index("mood"))
        self.assertLess(p.index("mood"), p.index("Candid editorial"))

    def test_history_changes_camera_and_palette(self):
        a, hist = self.analysis("red_carpet"), []
        seen = set()
        for i in range(6):
            r = prompt_writer.write_prompt(a, "candid_news_photo", hist, NAMES, None, f"article-{i}")
            seen.add((r["shot"], r["angle"]))
            hist.append({"shot": r["shot"], "angle": r["angle"], "lens": r["lens"], "palette": r["palette"], "prompt": r["prompt"]})
        self.assertGreaterEqual(len(seen), 5)  # six images, at least five different shot/angle pairs
        self.assertGreater(len({h["palette"] for h in hist[-3:]}), 1)  # the same palette is not repeated back to back

    def test_llm_never_sees_names_and_bad_prompts_fall_back(self):
        a = dict(self.analysis("wedding"), core_event="Elena Marlowe marries Tom Hargrove.")
        body = " ".join(["a bride walks"] * 20)
        llm = FakeLLM(prompts=[f"{body} like Elena Marlowe. A child smiles.", f"{body} Tom Hargrove. A boy runs."])
        r = prompt_writer.write_prompt(a, "candid_news_photo", [], NAMES, llm, "w")
        self.assertEqual(r["source"], "template")
        self.assertTrue(all("Marlowe" not in u and "Hargrove" not in u for u in llm.seen))
        self.assertEqual(len(r["notes"]), 2)

    def test_good_llm_prompt_is_used_after_cleaning(self):
        text = ("A bride in a long ivory gown seen from behind walks along a clifftop aisle lined with white roses, one hand holding a loose bouquet. "
                "Medium-wide shot, 35mm lens, slightly low angle, shallow depth of field. Golden-hour sun from low behind the guests lights the veil. "
                "Joyful, warm mood with an ivory and soft gold palette. Candid editorial news photograph with fine film grain. No text, no logos, no watermark.")
        r = prompt_writer.write_prompt(self.analysis("wedding"), "candid_news_photo", [], NAMES, FakeLLM(prompts=[text]), "w")
        self.assertEqual(r["source"], "llm")
        self.assertTrue(r["prompt"].endswith(concept.FINAL_SENTENCE))


class Mock(BaseHTTPRequestHandler):
    image_plan = []   # status codes to answer in order before success
    size_rejected = False
    quota = False     # answer 429s with the "daily free allocation" message
    strict = False    # behave like Cloudflare's real schnell schema: only prompt and steps are accepted
    bodies = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Mock.bodies.append((self.path, body))
        if "flux" in self.path:
            if Mock.image_plan:
                code = Mock.image_plan.pop(0)
                self.send_response(code)
                self.end_headers()
                self.wfile.write(b'{"errors":[{"message":"AiError: you have used up your daily free allocation of 10,000 neurons","code":4006}],"success":false}'
                                 if Mock.quota else b'{"success": false}')
                return
            if Mock.strict:
                extra = [k for k in ("seed", "width", "height") if k in body]
                if extra:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(json.dumps({"errors": [{"message": f"AiError: Bad input: Error: Additional or unevaluated properties '/{extra[0]}' at '/' not allowed", "code": 5006}], "success": False}).encode())
                    return
            if "width" in body and Mock.size_rejected:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"errors": "unknown param"}')
                return
            import base64
            out = json.dumps({"success": True, "result": {"image": base64.b64encode(png(1024, 1024)).decode()}}).encode()
        else:
            out = json.dumps({"success": True, "result": {"response": "{}"}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)


class Generator(unittest.TestCase):
    def setUp(self):
        Mock.image_plan, Mock.size_rejected, Mock.strict, Mock.quota, Mock.bodies = [], False, False, False, []
        self.srv = HTTPServer(("127.0.0.1", 0), Mock)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        patcher = mock.patch.dict(os.environ, {"CF_ACCOUNT_ID": "a", "CF_API_TOKEN": "t", "CF_API_BASE": f"http://127.0.0.1:{self.srv.server_port}", "IMG_STEPS": "8"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.srv.shutdown)
        generator._rejected.clear()
        p = mock.patch.object(generator, "_sleep", lambda s: None)
        p.start()
        self.addCleanup(p.stop)

    def test_steps_never_exceed_four_seed_is_sent_and_returned(self):
        raw, seed = generator.generate("a prompt", seed=1234)
        self.assertEqual(seed, 1234)
        body = Mock.bodies[0][1]
        self.assertEqual((body["steps"], body["seed"]), (4, 1234))  # IMG_STEPS=8 is clamped
        self.assertNotIn("guidance", body)
        self.assertEqual((body["width"], body["height"]), (1344, 768))

    def test_random_seed_by_default(self):
        self.assertNotEqual(generator.generate("p")[1], generator.generate("p")[1])

    def test_backoff_on_rate_limit_and_server_errors(self):
        Mock.image_plan = [429, 503]
        raw, _ = generator.generate("p")
        self.assertTrue(raw)
        self.assertEqual(len(Mock.bodies), 3)

    def test_gives_up_after_three_attempts(self):
        Mock.image_plan = [500, 500, 500]
        with self.assertRaises(generator.GenerationError):
            generator.generate("p")

    def test_size_rejected_retries_without_size(self):
        Mock.size_rejected = True
        generator.generate("p")
        self.assertIn("width", Mock.bodies[0][1])
        self.assertNotIn("width", Mock.bodies[1][1])

    def test_spent_daily_allowance_fails_at_once_without_backoff(self):
        Mock.image_plan, Mock.quota = [429, 429, 429], True
        slept = []
        with mock.patch.object(generator, "_sleep", slept.append), self.assertRaises(generator.GenerationError) as cm:
            generator.generate("p")
        self.assertIn("daily free allocation", str(cm.exception))
        self.assertEqual((len(Mock.bodies), slept), (1, []))

    def test_strict_api_drops_seed_and_size_one_field_at_a_time(self):
        Mock.strict = True
        raw, seed = generator.generate("p")
        self.assertIsNone(seed)  # the API has no seed input: nothing is claimed
        self.assertFalse(generator.seed_supported())
        self.assertEqual([sorted(b) for _, b in Mock.bodies][0], ["height", "prompt", "seed", "steps", "width"])
        self.assertEqual(sorted(Mock.bodies[-1][1]), ["prompt", "steps"])
        n = len(Mock.bodies)
        generator.generate("p")  # remembered: the next call goes out clean at once
        self.assertEqual(len(Mock.bodies), n + 1)

    def test_fit_crops_to_target_without_stretching(self):
        from PIL import Image
        webp, raw_size = generator.fit(png(1024, 1024), 1344, 768)
        self.assertEqual(raw_size, (1024, 1024))
        self.assertEqual(Image.open(io.BytesIO(webp)).size, (1344, 768))


class Checker(unittest.TestCase):
    A = {"core_event": "x", "emotion": "joyful", "setting": "y"}

    def test_blank_image_is_rejected_by_rules(self):
        self.assertTrue(any("blank" in r for r in checker.rule_check(png(flat=True))))
        self.assertEqual(checker.rule_check(png()), [])

    def test_vision_flags_reject_with_reasons(self):
        verdict = dict(GOOD_VERDICT, visible_text_or_logos=True, recognizable_real_person=True)
        qc = checker.check(png(), self.A, FakeLLM(verdicts=[verdict]))
        self.assertFalse(qc["passed"])
        self.assertIn("visible text or logos", qc["reasons"])
        self.assertIn("a clearly recognizable real person", qc["reasons"])

    def test_mood_mismatch_rejects(self):
        qc = checker.check(png(), self.A, FakeLLM(verdicts=[dict(GOOD_VERDICT, matches_story_mood=False)]))
        self.assertFalse(qc["passed"])

    def test_unavailable_vision_model_is_skipped_not_failed(self):
        qc = checker.check(png(), self.A, FakeLLM(verdicts=[llmmod.LLMError("licence not accepted")]))
        self.assertTrue(qc["passed"])
        self.assertFalse(qc["vision"]["ran"])
        self.assertIn("unavailable", qc["vision"]["skipped"])


class PipelineEndToEnd(unittest.TestCase):
    def setUp(self):
        Mock.image_plan, Mock.size_rejected, Mock.strict, Mock.quota, Mock.bodies = [], False, False, False, []
        self.srv = HTTPServer(("127.0.0.1", 0), Mock)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.dict(os.environ, {"CF_ACCOUNT_ID": "a", "CF_API_TOKEN": "t", "CF_API_BASE": f"http://127.0.0.1:{self.srv.server_port}",
                                               "IMG_META_DIR": self.tmp.name, "IMG_LLM_PROVIDER": "none"})
        patcher.start()
        generator._rejected.clear()
        for cleanup in (patcher.stop, self.srv.shutdown, self.tmp.cleanup):
            self.addCleanup(cleanup)

    ARTICLE = {"key": "2026-10-28-00-00-sample", "headline": "Elena Marlowe and Tom Hargrove marry near Byron Bay", "body": "They married at sunset.",
               "category": "Celebrity News", "names": ["Elena Marlowe", "Tom Hargrove"]}

    def test_full_run_saves_metadata_and_history(self):
        res = pipeline.run(self.ARTICLE, llm=None)
        self.assertTrue(res["ok"])
        self.assertEqual(res["analysis"]["story_type"], "wedding")
        for name in NAMES[:2]:
            self.assertNotIn(name, res["prompt"] + res["alt"])
        m = json.loads((Path(self.tmp.name) / "2026-10-28-00-00-sample.json").read_text())
        for k in ("article", "story_type", "prompt", "seed", "model", "timestamp", "quality", "preset", "alt"):
            self.assertIn(k, m)
        self.assertEqual(len(meta.load_history()), 1)
        self.assertEqual(Mock.bodies[0][1]["seed"], m["seed"])

    def test_rejected_image_is_regenerated_with_a_new_seed_then_passes(self):
        llm = FakeLLM(verdicts=[dict(GOOD_VERDICT, visible_text_or_logos=True), GOOD_VERDICT])
        res = pipeline.run(self.ARTICLE, llm=llm)
        self.assertTrue(res["ok"])
        self.assertEqual([a["passed"] for a in res["attempts"]], [False, True])
        self.assertNotEqual(res["attempts"][0]["seed"], res["attempts"][1]["seed"])

    def test_all_attempts_rejected_gives_no_image_and_no_history(self):
        bad = dict(GOOD_VERDICT, nudity=True)
        res = pipeline.run(self.ARTICLE, llm=FakeLLM(verdicts=[bad, bad, bad]))
        self.assertFalse(res["ok"])
        self.assertIsNone(res["webp"])
        self.assertEqual(len(res["attempts"]), 3)  # first try plus two retries
        self.assertEqual(meta.load_history(), [])

    def test_sensitive_story_gets_a_people_free_symbolic_scene(self):
        res = pipeline.run({"key": "s", "headline": "Veteran actress Margaret Ellison dies aged 84", "body": "She died peacefully at home.", "category": "News",
                            "names": ["Margaret Ellison"]}, llm=None)
        self.assertEqual(res["analysis"]["sensitivity"], "high_risk")
        self.assertEqual(concept.check_prompt(res["prompt"], NAMES, "high_risk"), [])
        self.assertNotRegex(res["prompt"].lower(), r"\b(woman|man|people|crowd|figure|silhouette)\b")


class LlmQuota(unittest.TestCase):
    def test_spent_allowance_is_not_retried(self):
        hits = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                hits.append(1)
                self.send_response(429)
                self.end_headers()
                self.wfile.write(b'{"errors":[{"message":"you have used up your daily free allocation of 10,000 neurons"}]}')

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        slept = []
        with mock.patch.object(llmmod, "_sleep", slept.append), self.assertRaises(llmmod.LLMError):
            llmmod.post_json(f"http://127.0.0.1:{srv.server_port}/x", {}, {})
        srv.shutdown()
        self.assertEqual((len(hits), slept), (1, []))


class AltAndCaption(unittest.TestCase):
    def test_alt_text_is_one_short_factual_sentence_without_names(self):
        a = dict(analyzer.heuristic("x"), story_type="wedding", setting="a clifftop venue with Elena Marlowe's guests")
        alt = publisher.alt_text(a, NAMES)
        self.assertNotIn("Marlowe", alt)
        self.assertLessEqual(len(alt), 126)
        self.assertTrue(alt.startswith("Illustration of") and alt.endswith("."))

    def test_long_alt_text_is_cut_at_a_phrase_not_mid_word(self):
        a = dict(analyzer.heuristic("x"), setting="a flower-covered wedding venue", key_objects=["wedding rings", "a long white veil", "roses"],
                 time_and_light="golden-hour sun from low behind the guests")
        alt = publisher.alt_text(a, NAMES)
        self.assertTrue(alt.endswith("a long white veil."), alt)

    def test_caption_can_be_turned_off(self):
        with mock.patch.dict(os.environ, {"IMG_CAPTION": "off"}):
            self.assertEqual(config.caption(), "")
        with mock.patch.dict(os.environ, {"IMG_CAPTION": "Illustration generated with AI"}):
            self.assertEqual(config.caption(), "Illustration generated with AI")


class GenerateImagesIntegration(unittest.TestCase):
    """The real generate_images.py on a temp copy of the repo: pipeline on, and the fallback when the pipeline is off."""

    def run_script(self, usage=None, **extra):
        srv = HTTPServer(("127.0.0.1", 0), Mock)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        Mock.bodies = []
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "articles").mkdir()
            subprocess.run(["cp", "-r", str(REPO / "agents"), str(root / "agents")], check=True)
            (root / "config.json").write_text(json.dumps({"ai_images": True, "celebrities": ["Elena Marlowe"]}))
            (root / "articles" / "2026-10-28-09-00-elena-marlowe.md").write_text(
                '---\ntitle: "Elena Marlowe weds Tom Hargrove"\nstatus: approved\nwp_status: pending\ncelebrity: "Elena Marlowe"\ncategories: ["Celebrity News"]\n'
                'image_prompt: "an empty cinema auditorium"\n---\n\nThey married on Saturday.\n')
            if usage is not None:
                (root / "articles" / "image-meta").mkdir()
                (root / "articles" / "image-meta" / "_usage.json").write_text(json.dumps(usage))
            env = dict(os.environ, CF_ACCOUNT_ID="a", CF_API_TOKEN="t", CF_API_BASE=f"http://127.0.0.1:{srv.server_port}", IMG_LLM_PROVIDER="none", **extra)
            r = subprocess.run([sys.executable, str(root / "agents" / "generate_images.py"), "--max", "5"], env=env, capture_output=True, text=True)
            front = (root / "articles" / "2026-10-28-09-00-elena-marlowe.md").read_text()
            meta_files = sorted(p.name for p in (root / "articles" / "image-meta").glob("*")) if (root / "articles" / "image-meta").exists() else []
            has_img = (root / "articles" / "images" / "2026-10-28-09-00-elena-marlowe.webp").exists()
            uf = root / "articles" / "image-meta" / "_usage.json"
            self.usage_after = json.loads(uf.read_text()) if uf.exists() else None
        srv.shutdown()
        return r, front, meta_files, has_img

    def test_pipeline_path(self):
        r, front, meta_files, has_img = self.run_script()
        self.assertIn("1 image(s) created", r.stdout, r.stderr)
        self.assertIn("wedding", r.stdout)
        self.assertIn("image_alt: \"Illustration of", front)
        self.assertNotIn("Marlowe", front.split("image_alt:")[1].split("\n")[0])
        self.assertIn("2026-10-28-09-00-elena-marlowe.json", meta_files)
        self.assertTrue(has_img)
        prompt = Mock.bodies[0][1]["prompt"]
        self.assertNotIn("cinema auditorium", prompt)  # built from the story, not the writer's one-liner
        self.assertNotIn("Marlowe", prompt)

    def test_usage_is_counted_and_the_daily_cap_stops_the_run(self):
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        r, front, meta_files, has_img = self.run_script()
        self.assertEqual(self.usage_after, {"date": today, "images": 1})
        r, front, meta_files, has_img = self.run_script(usage={"date": today, "images": 40})
        self.assertIn("daily image cap reached", r.stdout)
        self.assertFalse(has_img)
        self.assertEqual(Mock.bodies, [])  # not a single request was spent
        r, front, meta_files, has_img = self.run_script(usage={"date": "2000-01-01", "images": 999})  # an old day does not count
        self.assertTrue(has_img)
        r, front, meta_files, has_img = self.run_script(usage={"date": today, "images": 5}, IMG_DAILY_IMAGE_CAP="5")
        self.assertIn("daily image cap reached", r.stdout)

    def test_pipeline_switched_off_keeps_the_old_scene_prompt(self):
        r, front, meta_files, has_img = self.run_script(IMG_ENABLED="false")
        self.assertIn("1 image(s) created", r.stdout, r.stderr)
        self.assertIn("an empty cinema auditorium", Mock.bodies[0][1]["prompt"])
        self.assertEqual([f for f in meta_files if not f.startswith("_")], [])  # no per-article metadata; only the usage counter


if __name__ == "__main__":
    unittest.main()
