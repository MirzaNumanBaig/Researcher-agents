"""Article -> Image pipeline: analyzer JSON parsing, safety rules, prompt quality, generator retries, quality check, end to end (mock servers)."""
import io
import json
import os
import re
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
from imagegen import analyzer, blueprint, cast, checker, concept, config, finish, generator, meta, pipeline, prompt_writer, publisher  # noqa: E402
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


GOOD_VERDICT = {"face_naturalness": 5, "expression_match": 5, "hands_anatomy": 5, "composition_match": 5, "realism": 5, "no_text_or_logos": 5,
                "recognizable_real_person": False, "nudity": False, "graphic_injury": False, "notes": "fine"}


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

    def test_the_headline_decides_the_type_not_a_passing_mention_in_the_body(self):
        a = analyzer.heuristic("Harbour Lights, starring Jack Dunmore, gets a 12 December cinema release", "A first trailer is due next week.", "Movies")
        self.assertEqual(a["story_type"], "film_release")
        self.assertEqual(analyzer.heuristic("A new look at the picture", "It will premiere soon at a cinema near you.")["story_type"], "film_release")  # body used when the headline says nothing

    def test_unusable_llm_answer_falls_back_to_rules(self):
        a = analyzer.analyze("Couple marry on a clifftop", "", "", llm=FakeLLM(analysis=None))
        self.assertEqual((a["story_type"], a["source"]), ("wedding", "rules"))

    def test_good_llm_answer_is_used(self):
        raw = {"story_type": "film_release", "core_event": "A film gets a date.", "emotion": "anticipatory", "setting": "film set", "key_objects": ["a clapperboard", "a reel", "a lens"],
               "time_and_light": "a bright projector beam", "palette": ["deep blue", "gold"], "sensitivity": "safe"}
        a = analyzer.analyze("Film date", "", "", llm=FakeLLM(analysis=raw))
        self.assertEqual((a["story_type"], a["source"], a["setting"]), ("film_release", "llm", "film set"))


class RedCarpetRule(unittest.TestCase):
    def test_a_red_carpet_headline_is_a_red_carpet_story_even_when_it_says_film(self):
        a = analyzer.heuristic("Nina Calloway and Marcus Reid walk the red carpet together at the Sydney film gala")
        self.assertEqual(a["story_type"], "red_carpet")
        self.assertEqual(blueprint.default_blueprint(a)["people_count"], 2)
        self.assertEqual(analyzer.heuristic("New film sequel gets a December cinema release")["story_type"], "film_release")


class SafetyRules(unittest.TestCase):
    def test_strip_names_full_surname_and_shared_words(self):
        clean, removed = concept.strip_names("Elena Marlowe and later Hargrove stand together", NAMES)
        self.assertNotIn("Marlowe", clean)
        self.assertNotIn("Hargrove", clean)
        self.assertIn("an anonymous figure", clean)
        self.assertEqual(concept.strip_names("A short walk past a fox", ["Martin Short", "Michael J. Fox"])[0], "A short walk past a fox")  # common words survive

    def test_places_adjectives_and_titles_are_not_mistaken_for_names(self):
        names = concept.known_names("Veteran Australian actress Margaret Ellison dies aged 84")
        self.assertIn("Margaret Ellison", names)
        self.assertNotIn("Veteran Australian", names)
        names = concept.known_names("Elena Marlowe and Tom Hargrove marry in a clifftop ceremony near Byron Bay")
        self.assertNotIn("Byron Bay", names)
        self.assertIn("Elena Marlowe", names)
        self.assertNotIn("Byron Bay", concept.known_names("Stars arrive at Bondi Beach and Gold Coast events"))
        self.assertNotIn("Coast Hotel", concept.known_names("Cast dines in Coast Hotel"))  # a pair after a place cue

    def test_sanitize_removes_syntax_likeness_and_text_requests(self):
        dirty = ("A (woman:1.3) who looks like Elena Marlowe holds a sign reading HELLO, in the style of a famous painter. "
                 "Negative prompt: blurry. A poster and a billboard behind. No text, no logos.")
        s = concept.sanitize_prompt(dirty, NAMES)
        for bad in ("Marlowe", "looks like", ":1.3", "Negative", "HELLO", "poster", "billboard", "style of"):
            self.assertNotIn(bad, s)
        self.assertTrue(s.endswith(concept.FINAL_SENTENCE))
        self.assertEqual(s.count("No text"), 1)

    def test_check_prompt_flags_names_children_people_and_length(self):
        base = " ".join(["quiet"] * 95) + ". " + concept.FINAL_SENTENCE
        self.assertEqual(concept.check_prompt(base, NAMES), [])
        self.assertTrue(any("words" in p for p in concept.check_prompt(" ".join(["quiet"] * 70) + ". " + concept.FINAL_SENTENCE, NAMES)))  # people prompts need 90+
        self.assertEqual(concept.check_prompt(" ".join(["quiet"] * 70) + ". " + concept.FINAL_SENTENCE, NAMES, people=False), [])  # object scenes need 60+
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
                self.assertEqual(concept.check_prompt(p, NAMES, sens if concept.is_sensitive(a) else "safe", people=False), [], (kind, sens, p))
                self.assertTrue(60 <= concept.words(p) <= 120, (kind, concept.words(p)))

    def test_no_prop_is_named_twice(self):
        for kind in analyzer.STORY_TYPES:
            p = prompt_writer.write_prompt(self.analysis(kind), "candid_news_photo", [], NAMES, None, kind)["prompt"].lower()
            p = re.sub(r"lit by [^.]*\.", "", p)  # the named light source may be one of the props (camera flashes, a projector beam)
            for prop in analyzer.DEFAULTS[kind][2]:
                self.assertLessEqual(p.count(prop.lower()), 1, (kind, prop, p))

    def test_foreground_prop_does_not_repeat_the_scene_noun(self):
        for kind, sens in (("tribute", "high_risk"), ("film_release", "safe")):
            p = prompt_writer.write_prompt(self.analysis(kind, sens), "candid_news_photo", [], NAMES, None, kind)["prompt"]
            subject, fg = p.split(". Softly out of focus in the foreground: ")[0], p.split("foreground: ")[1].split(".")[0]
            self.assertFalse(prompt_writer._used(fg, subject), (kind, subject, fg))

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
        self.assertEqual((body["width"], body["height"]), (1536, 864))  # generated at 1536x864 (16:9, multiples of 32)

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


class Checker(unittest.TestCase):
    A = {"core_event": "x", "emotion": "joyful", "setting": "y"}

    def test_blank_image_is_rejected_by_rules(self):
        self.assertTrue(any("blank" in r for r in checker.rule_check(png(flat=True))))
        self.assertEqual(checker.rule_check(png()), [])

    def test_any_score_under_four_rejects_with_the_reason(self):
        qc = checker.check(png(), self.A, FakeLLM(verdicts=[dict(GOOD_VERDICT, face_naturalness=3, no_text_or_logos=2)]))
        self.assertFalse(qc["passed"])
        self.assertIn("face naturalness scored 3/5", qc["reasons"])
        self.assertIn("no visible text or logos scored 2/5", qc["reasons"])
        self.assertEqual(qc["scores"]["realism"], 5)

    def test_all_fours_and_fives_pass_and_scores_are_kept(self):
        qc = checker.check(png(), self.A, FakeLLM(verdicts=[dict(GOOD_VERDICT, realism=4, hands_anatomy=4)]))
        self.assertTrue(qc["passed"])
        self.assertEqual(len(qc["scores"]), 6)

    def test_the_minimum_score_is_a_setting(self):
        with mock.patch.dict(os.environ, {"IMG_MIN_SCORE": "5"}):
            self.assertFalse(checker.check(png(), self.A, FakeLLM(verdicts=[dict(GOOD_VERDICT, realism=4)]))["passed"])

    def test_safety_flags_still_reject(self):
        qc = checker.check(png(), self.A, FakeLLM(verdicts=[dict(GOOD_VERDICT, recognizable_real_person=True, nudity=True)]))
        self.assertFalse(qc["passed"])
        self.assertIn("a clearly recognizable real person", qc["reasons"])

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
        for k in ("article", "story_type", "prompt", "seed", "model", "timestamp", "quality", "preset", "alt", "scene_blueprint", "stand_ins", "finish"):
            self.assertIn(k, m)
        self.assertIs(m["ai_generated"], True)  # the AI flag lives in the log, not on the page
        self.assertEqual(m["caption"], "")
        self.assertEqual(len(res["stand_ins"]), 2)
        self.assertEqual(len(meta.load_history()), 1)
        self.assertEqual(Mock.bodies[0][1]["seed"], m["seed"])

    def test_rejected_image_is_regenerated_with_a_new_seed_then_passes(self):
        llm = FakeLLM(verdicts=[dict(GOOD_VERDICT, no_text_or_logos=2), GOOD_VERDICT])
        res = pipeline.run(self.ARTICLE, llm=llm)
        self.assertTrue(res["ok"])
        self.assertEqual([a["passed"] for a in res["attempts"]], [False, True])
        self.assertNotEqual(res["attempts"][0]["seed"], res["attempts"][1]["seed"])

    def test_all_attempts_rejected_gives_no_image_and_no_history(self):
        bad = dict(GOOD_VERDICT, realism=2)
        res = pipeline.run(self.ARTICLE, llm=FakeLLM(verdicts=[bad, bad, bad, bad]))
        self.assertFalse(res["ok"])
        self.assertIsNone(res["image"])
        self.assertEqual(len(res["attempts"]), 4)  # first try, two retries, then the symbolic fallback (also rejected here)
        self.assertEqual(meta.load_history(), [])

    def test_three_rejected_face_led_attempts_fall_back_to_a_symbolic_scene(self):
        bad = dict(GOOD_VERDICT, face_naturalness=2)
        res = pipeline.run(self.ARTICLE, llm=FakeLLM(verdicts=[bad, bad, bad, GOOD_VERDICT]))
        self.assertTrue(res["ok"])
        self.assertEqual(res["fallback"], "symbolic")
        self.assertEqual(len(res["attempts"]), 4)
        self.assertEqual(res["stand_ins"], [])
        self.assertNotRegex(res["prompt"].lower(), r"\b(woman|man|people|face|brows)\b")
        self.assertEqual(meta.load_history()[-1]["cast"], [])

    def test_final_image_is_1600x900_webp_and_no_caption_is_set(self):
        from PIL import Image
        res = pipeline.run(self.ARTICLE, llm=None)
        im = Image.open(io.BytesIO(res["image"]))
        self.assertEqual((im.size, im.format, res["ext"]), ((1600, 900), "WEBP", "webp"))
        self.assertEqual(res["caption"], "")
        self.assertEqual(res["finish"]["size"], [1600, 900])

    def test_blueprint_from_the_news_photo_is_used_when_reference_images_are_on(self):
        vision = dict(shot_size="medium", angle="eye-level", people=[{"gender_presentation": "woman", "age_range": "late 20s", "facial_expression": {"eyebrows": "raised", "eyes": "glassy", "mouth": "pressed", "jaw": "tense"},
                                                                      "gaze": "down", "head": "bowed", "posture": "rounded shoulders", "hands": "in pockets", "clothing": "a camel coat"}], setting="a rain-wet street")
        llm = FakeLLM(verdicts=[vision, GOOD_VERDICT])
        with mock.patch.dict(os.environ, {"IMG_REFERENCE_IMAGES": "true"}), mock.patch.object(pipeline, "fetch_reference", return_value=(b"x", "image/jpeg")):
            res = pipeline.run(self.ARTICLE, llm=llm)
        self.assertEqual(res["blueprint"]["source"], "vision")
        self.assertEqual(res["blueprint"]["people_count"], 1)
        self.assertIn("glassy", res["prompt"])

    def test_sensitive_story_gets_a_people_free_symbolic_scene(self):
        res = pipeline.run({"key": "s", "headline": "Veteran actress Margaret Ellison dies aged 84", "body": "She died peacefully at home.", "category": "News",
                            "names": ["Margaret Ellison"]}, llm=None)
        self.assertEqual(res["analysis"]["sensitivity"], "high_risk")
        self.assertEqual((res["blueprint"]["people_count"], res["stand_ins"]), (0, []))
        self.assertEqual(concept.check_prompt(res["prompt"], NAMES, "high_risk", people=False), [])
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


class Finish(unittest.TestCase):
    def test_default_output_is_1600x900_webp_upscaled_from_the_raw_size(self):
        from PIL import Image
        data, info = finish.finish(png(1536, 864))
        im = Image.open(io.BytesIO(data))
        self.assertEqual((im.size, im.format), ((1600, 900), "WEBP"))
        self.assertEqual((info["raw_size"], info["upscaled_size"], info["upscaler"]), ([1536, 864], [3072, 1728], "lanczos"))

    def test_a_square_raw_image_is_cropped_not_stretched(self):
        from PIL import Image
        data, info = finish.finish(png(1024, 1024))
        self.assertEqual(Image.open(io.BytesIO(data)).size, (1600, 900))
        self.assertEqual(info["raw_size"], [1024, 1024])

    def test_size_format_and_upscaler_come_from_settings(self):
        from PIL import Image
        with mock.patch.dict(os.environ, {"IMG_OUT_WIDTH": "1920", "IMG_OUT_HEIGHT": "1080", "IMG_OUT_FORMAT": "jpeg", "IMG_UPSCALER": "none"}):
            data, info = finish.finish(png(1536, 864))
        im = Image.open(io.BytesIO(data))
        self.assertEqual((im.size, im.format, info["ext"], info["upscaler"]), ((1920, 1080), "JPEG", "jpg", "none"))

    def test_quality_is_lowered_until_the_file_fits_but_never_below_the_floor(self):
        noisy = png(1536, 864)
        with mock.patch.dict(os.environ, {"IMG_MAX_KB": "1"}):  # impossible budget: the floor wins
            _, info = finish.finish(noisy)
        self.assertEqual(info["quality"], config.get("min_quality"))
        with mock.patch.dict(os.environ, {"IMG_MAX_KB": "100000"}):
            self.assertEqual(finish.finish(noisy)[1]["quality"], config.get("out_quality"))

    def test_jpeg_keeps_quality_90_or_more_when_it_fits(self):
        with mock.patch.dict(os.environ, {"IMG_OUT_FORMAT": "jpg", "IMG_MAX_KB": "100000"}):
            self.assertGreaterEqual(finish.finish(png(1536, 864))[1]["quality"], 90)

    def test_realesrgan_runs_the_command_and_falls_back_to_lanczos_when_missing(self):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            from PIL import Image
            Image.open(cmd[2]).resize((3072, 1728)).save(cmd[4])  # -i in -o out
            return subprocess.CompletedProcess(cmd, 0)

        with mock.patch.dict(os.environ, {"IMG_UPSCALER": "realesrgan", "IMG_UPSCALE_CMD": "python3 -i {input} -o {output} -s {scale}"}), \
                mock.patch.object(finish, "_run", fake_run):
            _, info = finish.finish(png(1536, 864))
        self.assertEqual(info["upscaler"], "realesrgan")
        self.assertIn("-s", calls[0])
        self.assertEqual(calls[0][-1], "2")
        with mock.patch.dict(os.environ, {"IMG_UPSCALER": "realesrgan", "IMG_UPSCALE_CMD": "no-such-program-xyz -i {input} -o {output}"}):
            self.assertEqual(finish.finish(png(1536, 864))[1]["upscaler"], "lanczos")

    def test_finishing_is_light(self):
        from PIL import Image, ImageChops, ImageStat
        base = Image.open(io.BytesIO(png(1600, 900))).convert("RGB")
        out = finish.polish(base.copy())
        diff = ImageStat.Stat(ImageChops.difference(base, out)).mean
        self.assertLess(max(diff), 8)  # grain and sharpening move the average pixel by only a few levels
        with mock.patch.dict(os.environ, {"IMG_SHARPEN": "0", "IMG_GRAIN": "0"}):
            self.assertEqual(list(finish.polish(base.copy()).getdata())[:50], list(base.getdata())[:50])

    def test_face_restoration_is_off_by_default_and_a_failure_keeps_the_original(self):
        from PIL import Image
        img = Image.open(io.BytesIO(png(400, 300)))
        self.assertEqual(finish.restore_faces(img)[1], False)
        with mock.patch.dict(os.environ, {"IMG_FACE_RESTORE": "command", "IMG_FACE_RESTORE_CMD": "no-such-restorer {input} {output}"}):
            out, done = finish.restore_faces(img)
        self.assertFalse(done)
        self.assertIs(out, img)


VISION = {"shot_size": "extreme close-up", "angle": "low angle", "lens_feel": "85mm", "camera_height": "chest height",
          "composition": {"layout": "two people on the left third", "leading_lines": "the carpet edge", "depth_layers": {"foreground": "a rope", "midground": "the pair", "background": "flashes"}},
          "people_count": 3,
          "people": [{"gender_presentation": "woman", "age_range": "early 30s", "facial_expression": {"eyebrows": "inner brows raised", "eyes": "glassy", "mouth": "lips pressed", "jaw": "slight tension"},
                      "gaze": "off-frame left", "head": "tilted", "posture": "shoulders rounded", "hands": "holding a clutch", "interaction": "standing a metre from the man",
                      "clothing": "an emerald satin gown"},
                     {"gender_presentation": "man", "age_range": "late 30s", "facial_expression": {"eyebrows": "level", "eyes": "steady", "mouth": "closed", "jaw": "set"},
                      "gaze": "at the camera", "head": "turned", "posture": "upright", "hands": "in a pocket", "clothing": "a black tuxedo"},
                     {"gender_presentation": "man", "age_range": "40s", "facial_expression": {}, "gaze": "x", "head": "x", "posture": "x", "hands": "x"}],
          "setting": "a red carpet at night", "props": ["velvet ropes", "camera flashes"], "time_of_day": "night", "light": {"source": "camera flashes", "direction": "from the front"},
          "palette": ["emerald", "gold"], "mood": "tense"}


class Blueprint(unittest.TestCase):
    A = dict(analyzer.heuristic("Nina Calloway and Marcus Reid walk the red carpet"), story_type="red_carpet", sensitivity="safe")

    def test_vision_json_is_parsed_capped_at_two_people_and_close_ups_softened(self):
        bp = blueprint.normalize(VISION, self.A, ["Nina Calloway"])
        self.assertEqual((bp["people_count"], len(bp["people"])), (2, 2))
        self.assertEqual(bp["shot_size"], "medium close-up")  # never an extreme close-up
        self.assertEqual(bp["people"][0]["facial_expression"]["jaw"], "slight tension")
        self.assertEqual(bp["people"][0]["clothing"], "an emerald satin gown")
        self.assertEqual(bp["light"]["source"], "camera flashes")

    def test_names_and_identity_traits_are_removed(self):
        raw = dict(VISION, setting="the red carpet where Nina Calloway poses")
        raw["people"] = [dict(VISION["people"][0], gaze="at the camera, round face, hooked nose", clothing="a gown that makes her look like a famous star, emerald silk")]
        bp = blueprint.normalize(raw, self.A, ["Nina Calloway"])
        flat = json.dumps(bp)
        for banned in ("Calloway", "hooked", "round face", "famous", "look like"):
            self.assertNotIn(banned, flat)

    def test_sensitive_stories_lose_all_people(self):
        sensitive = dict(self.A, story_type="tribute", sensitivity="high_risk")
        self.assertEqual(blueprint.normalize(VISION, sensitive, [])["people"], [])
        self.assertEqual(blueprint.default_blueprint(sensitive)["people_count"], 0)

    def test_garbage_or_missing_fields_fall_back_to_the_story_defaults(self):
        self.assertEqual(blueprint.normalize("nonsense", self.A, [])["source"], "template")
        bp = blueprint.normalize({"people": [{"gender_presentation": "robot"}]}, self.A, [])
        self.assertEqual(bp["people"][0]["gender_presentation"], "unspecified")
        self.assertTrue(bp["people"][0]["facial_expression"]["eyes"])
        self.assertTrue(bp["setting"])

    def test_reply_parsing_tolerates_fences_and_unusable_replies_return_none(self):
        class L:
            def vision(self, *a, **k):
                return "```json\n" + json.dumps(VISION) + "\n```"
        self.assertEqual(blueprint.from_reference(b"img", self.A, [], L())["people_count"], 2)

        class Bad:
            def vision(self, *a, **k):
                return "I cannot help with that"
        self.assertIsNone(blueprint.from_reference(b"img", self.A, [], Bad()))
        self.assertIsNone(blueprint.from_reference(None, self.A, [], L()))

    def test_every_people_story_type_has_a_full_body_language_card(self):
        for kind, (n, _, _) in blueprint.PLAN.items():
            bp = blueprint.default_blueprint(dict(self.A, story_type=kind, emotion="joyful"))
            self.assertEqual(bp["people_count"], n, kind)
            for p in bp["people"]:
                self.assertTrue(all(p["facial_expression"][k] for k in ("eyebrows", "eyes", "mouth", "jaw")), kind)
                self.assertTrue(all(p[k] for k in ("gaze", "head", "posture", "hands")), kind)


class Cast(unittest.TestCase):
    def test_cast_file_has_8_to_12_fictional_cards_with_no_real_names(self):
        cards = cast.load()
        self.assertTrue(8 <= len(cards) <= 12)
        self.assertEqual(len({c["id"] for c in cards}), len(cards))
        self.assertTrue({"woman", "man"} <= {c["presentation"] for c in cards})
        self.assertGreaterEqual(len({c["skin"] for c in cards}), 8)  # skin tone variety
        for c in cards:
            self.assertEqual(concept.names_in(json.dumps(c), NAMES), [])

    def test_two_people_get_two_different_cards_matching_presentation_and_age(self):
        bp = {"people": [{"gender_presentation": "woman", "age_range": "late 20s", "clothing": "an emerald gown"}, {"gender_presentation": "man", "age_range": "late 40s", "clothing": ""}]}
        a = cast.assign(bp, [], "k")
        self.assertEqual([s["presentation"] for s in a], ["woman", "man"])
        self.assertNotEqual(a[0]["id"], a[1]["id"])
        self.assertRegex(a[0]["descriptor"], r"(early|mid|late) (20|30)s")  # within about five years of the blueprint age
        self.assertRegex(a[1]["descriptor"], r"(mid|late) (40|50)s|early 40s")

    def test_descriptions_have_no_names_no_likeness_words_and_no_clothes(self):
        for c in cast.load():
            d = cast.describe(c)
            self.assertNotRegex(d.lower(), r"looks? like|resembl|famous|wearing")
            self.assertTrue(d.startswith("a woman") or d.startswith("a man"))

    def test_least_recently_used_cards_are_chosen_so_the_site_shows_varied_people(self):
        bp = {"people": [{"gender_presentation": "woman", "age_range": "", "clothing": ""}]}
        seen, history = [], []
        for i in range(5):
            a = cast.assign(bp, history, f"k{i}")
            seen.append(a[0]["id"])
            history.append({"cast": [a[0]["id"]]})
        self.assertEqual(len(set(seen)), 5)

    def test_clothing_hint_picks_the_closest_style(self):
        card = next(c for c in cast.load() if c["id"] == "cast-01")
        self.assertEqual(cast._style(card, "a fitted black satin dress", "k"), "a black satin dress")
        self.assertIn(cast._style(card, "", "k"), card["styles"])


class PeoplePrompt(unittest.TestCase):
    def build(self, kind, llm=None, history=()):
        a = dict(analyzer.heuristic("headline"), story_type=kind, sensitivity="safe")
        emo, setting, objs, light, pal = analyzer.DEFAULTS[kind]
        a.update(emotion=emo, setting=setting, key_objects=list(objs), time_and_light=light, palette=list(pal))
        bp = blueprint.default_blueprint(a)
        st = cast.assign(bp, list(history), kind)
        return a, bp, st, prompt_writer.write_prompt(a, "candid_news_photo", list(history), NAMES, llm, kind, bp, st)

    def test_every_people_story_type_makes_a_valid_prompt_in_the_specified_order(self):
        order = ["A ", "brows", "head ", "wears", "The setting is", "mm lens", "Lit by", "mood", "Natural skin texture", "No text, no logos, no watermark."]
        for kind in blueprint.PLAN:
            a, bp, st, r = self.build(kind)
            p = r["prompt"]
            self.assertEqual(concept.check_prompt(p, NAMES, "safe", people=True), [], (kind, p))
            self.assertTrue(90 <= concept.words(p) <= 200, (kind, concept.words(p)))
            self.assertLessEqual(len(st), 2)
            pos = [p.find(x) for x in order]
            self.assertTrue(all(i >= 0 for i in pos), (kind, [o for o, i in zip(order, pos) if i < 0]))
            self.assertEqual(pos, sorted(pos), (kind, p))
            self.assertNotRegex(p.lower(), r"\b(masterpiece|ultra-detailed|8k)\b")
            self.assertNotRegex(p, r"extreme close")

    def test_only_medium_shots_and_simple_hands_for_people(self):
        for i in range(8):
            r = self.build("red_carpet", history=[{"shot": "medium shot", "angle": "eye-level", "lens": "50mm"}] * i)[3]
            self.assertIn(r["shot"], prompt_writer.PEOPLE_SHOTS)
            self.assertNotIn("close-up", r["shot"])
        for kind in blueprint.PLAN:
            self.assertNotRegex(self.build(kind)[3]["prompt"].lower(), r"interlaced|fingers spread|clasped fingers")

    def test_llm_prompt_gets_the_stand_in_cards_and_never_a_name(self):
        llm = FakeLLM(prompts=["x"] * 2)
        a, bp, st, r = self.build("relationship", llm)
        user = llm.seen[0]
        self.assertIn(st[0]["descriptor"], user)
        self.assertIn("facial_expression", user)
        self.assertIn("Realism tail", user)
        self.assertEqual(concept.names_in(user, NAMES), [])
        self.assertEqual(r["source"], "template")  # "x" is not a valid prompt, so the template took over

    def test_good_llm_people_prompt_is_cleaned_and_used(self):
        a, bp, st, template = self.build("relationship")
        text = template["prompt"].replace("No text, no logos, no watermark.", "").strip() + " Looks like Elena Marlowe (famous:1.3)."
        a, bp, st, r = self.build("relationship", FakeLLM(prompts=[text]))
        self.assertEqual(r["source"], "llm")
        self.assertNotIn("Marlowe", r["prompt"])
        self.assertTrue(r["prompt"].endswith(concept.FINAL_SENTENCE))

    def test_sensitive_stories_never_get_people_even_with_a_blueprint(self):
        a = dict(self.build("red_carpet")[0], sensitivity="high_risk")
        bp = blueprint.normalize(VISION, a, [])
        r = prompt_writer.write_prompt(a, "candid_news_photo", [], NAMES, None, "k", bp, [{"id": "cast-01", "presentation": "woman", "descriptor": "a woman", "style": "x", "label": "The woman"}])
        self.assertNotRegex(r["prompt"].lower(), r"\b(woman|man|people|face|brows|skin)\b")


class NoVisibleCaption(unittest.TestCase):
    def test_caption_is_off_by_default_and_a_setting_turns_it_on(self):
        self.assertEqual(config.caption(), "")
        self.assertEqual(config.DEFAULTS["caption"], "")
        with mock.patch.dict(os.environ, {"IMG_CAPTION": "Image: AI"}):
            self.assertEqual(config.caption(), "Image: AI")

    def test_wordpress_upload_uses_an_empty_caption_unless_switched_on(self):
        code = ("import sys,os; sys.path.insert(0,'agents'); import publish_wordpress as p; print(repr(p.image_caption()))")
        for env, want in (({}, "''"), ({"IMG_CAPTION": "off"}, "''"), ({"IMG_CAPTION": "AI image"}, "'AI image'")):
            e = {k: v for k, v in os.environ.items() if k != "IMG_CAPTION"}
            r = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=dict(e, **env), capture_output=True, text=True)
            self.assertEqual(r.stdout.strip(), want, r.stderr)

    def test_no_visible_ai_wording_in_the_alt_text_or_the_prompt_sources(self):
        a = dict(analyzer.heuristic("x"), story_type="red_carpet", setting="a red carpet at night", time_and_light="camera flashes")
        bp = blueprint.default_blueprint(a)
        alt = publisher.alt_text(a, NAMES, bp, cast.assign(bp, [], "k"))
        self.assertRegex(alt, r"^Illustration of a (woman|man) and a (man|woman)|^Illustration of two (women|men)")
        self.assertLessEqual(len(alt), 126)
        self.assertNotRegex(alt, r"AI|generated|credit")


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
