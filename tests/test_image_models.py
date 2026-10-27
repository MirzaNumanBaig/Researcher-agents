"""Per-model image request settings: python3 -m unittest discover tests"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents"))
import generate_images as gi  # noqa: E402


class BuildBody(unittest.TestCase):
    def test_dreamshaper_keeps_its_old_request(self):
        b = gi.build_body("@cf/lykon/dreamshaper-8-lcm", "a stage", 1536, 896)
        self.assertEqual((b["num_steps"], b["width"], b["height"]), (8, 1536, 896))
        self.assertNotIn("guidance", b)

    def test_lucid_origin(self):
        b = gi.build_body("@cf/leonardo/lucid-origin", "a stage", 1536, 896)
        self.assertEqual((b["steps"], b["guidance"]), (25, 4.5))
        self.assertNotIn("num_steps", b)
        self.assertNotIn("negative_prompt", b)

    def test_phoenix_has_negative_prompt_and_num_steps(self):
        b = gi.build_body("@cf/leonardo/phoenix-1.0", "a stage", 1536, 896)
        self.assertEqual((b["num_steps"], b["guidance"]), (25, 2))
        self.assertIn("faces", b["negative_prompt"])
        self.assertLessEqual(b["width"], 2048)

    def test_unknown_model_falls_back_and_steps_can_be_overridden(self):
        self.assertEqual(gi.build_body("@cf/other/model", "x", 1024, 576)["num_steps"], 8)
        with mock.patch.dict(os.environ, {"CF_IMAGE_STEPS": "12"}):
            self.assertEqual(gi.build_body("@cf/leonardo/lucid-origin", "x", 1024, 576)["steps"], 12)

    def test_prompt_gets_the_style_suffix(self):
        self.assertTrue(gi.build_body("@cf/leonardo/lucid-origin", "a stage", 1024, 576)["prompt"].startswith("a stage, "))


if __name__ == "__main__":
    unittest.main()
