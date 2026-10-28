"""Per-model image request settings: python3 -m unittest discover tests"""
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "agents"))
import generate_images as gi  # noqa: E402

KLEIN, SCHNELL, DREAM = "@cf/black-forest-labs/flux-2-klein-4b", "@cf/black-forest-labs/flux-1-schnell", "@cf/lykon/dreamshaper-8-lcm"


class BuildBody(unittest.TestCase):
    def test_dreamshaper_keeps_its_old_request(self):
        b = gi.build_body(DREAM, "a stage", 1536, 896)
        self.assertEqual((b["num_steps"], b["width"], b["height"]), (8, 1536, 896))

    def test_klein_has_size_but_no_steps(self):
        b = gi.build_body(KLEIN, "a stage", 1024, 576)
        self.assertEqual((b["width"], b["height"]), (1024, 576))
        self.assertNotIn("steps", b)
        self.assertNotIn("num_steps", b)

    def test_schnell_has_steps_and_no_size(self):
        b = gi.build_body(SCHNELL, "a stage", 1536, 896)
        self.assertEqual(b["steps"], 4)
        self.assertNotIn("width", b)
        self.assertNotIn("height", b)

    def test_unknown_model_falls_back_and_steps_can_be_overridden(self):
        self.assertEqual(gi.build_body("@cf/other/model", "x", 1024, 576)["num_steps"], 8)
        with mock.patch.dict(os.environ, {"CF_IMAGE_STEPS": "6"}):
            self.assertEqual(gi.build_body(SCHNELL, "x", 1024, 576)["steps"], 6)

    def test_prompt_gets_the_style_suffix(self):
        self.assertTrue(gi.build_body(KLEIN, "a stage", 1024, 576)["prompt"].startswith("a stage, "))


class EncodeAndSize(unittest.TestCase):
    def test_klein_is_multipart_others_json(self):
        data, ctype = gi.encode(KLEIN, {"prompt": "a stage", "width": 1024})
        self.assertTrue(ctype.startswith("multipart/form-data; boundary="))
        self.assertIn(b'name="prompt"\r\n\r\na stage', data)
        self.assertEqual(gi.encode(SCHNELL, {"prompt": "x"})[1], "application/json")
        self.assertEqual(gi.encode(DREAM, {"prompt": "x"})[1], "application/json")

    def test_generation_size(self):
        self.assertEqual(gi.gen_size(KLEIN), (1024, 576))
        self.assertEqual(gi.gen_size(DREAM), (1536, 896))
        with mock.patch.dict(os.environ, {"CF_GEN_WIDTH": "1280", "CF_GEN_HEIGHT": "768"}):
            self.assertEqual(gi.gen_size(KLEIN), (1280, 768))


if __name__ == "__main__":
    unittest.main()


class DefaultModel(unittest.TestCase):
    def test_default_is_flux_2_klein_4b(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CF_IMAGE_MODEL", "IMG_"))}
        code = "import sys; sys.path.insert(0, 'agents'); import generate_images as g; from imagegen import config; print(g.MODEL, config.get('image_model'))"
        out = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True).stdout.split()
        self.assertEqual(out, [KLEIN, KLEIN])
