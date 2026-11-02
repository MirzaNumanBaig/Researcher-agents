"""A real photo is never used twice; Rank Math fields are read, checked and sent (python3 -m unittest discover tests)."""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "agents"))
import check_article  # noqa: E402
import generate_images as gi  # noqa: E402
import publish_wordpress as pw  # noqa: E402

PHOTOS = [{"page": "https://commons.wikimedia.org/wiki/File:A.jpg"}, {"page": "https://commons.wikimedia.org/wiki/File:B.jpg"}]


class UniquePhoto(unittest.TestCase):
    def test_skips_used_and_runs_out(self):
        self.assertEqual(gi.pick_photo(PHOTOS, set())["page"], PHOTOS[0]["page"])
        self.assertEqual(gi.pick_photo(PHOTOS, {PHOTOS[0]["page"]})["page"], PHOTOS[1]["page"])
        self.assertIsNone(gi.pick_photo(PHOTOS, {p["page"] for p in PHOTOS}))
        self.assertIsNone(gi.pick_photo([], set()))


class Seo(unittest.TestCase):
    FRONT = 'title: "Nicole Kidman returns"\ndescription: "Short."\nseo_title: "T"\nseo_description: "D"\nfocus_keyword: "Nicole Kidman"\npermalink: "Nicole Kidman: Practical Magic 2!"\ncelebrity: "Nicole Kidman"'

    def test_fields_and_slug(self):
        self.assertEqual(pw.seo_fields(self.FRONT), ("T", "D", "Nicole Kidman", "nicole-kidman-practical-magic-2"))

    def test_fallbacks(self):
        t, d, k, s = pw.seo_fields('title: "H"\ndescription: "X"\ncelebrity: "A B"')
        self.assertEqual((t, d, k, s), ("H", "X", "A B", ""))

    def test_checker(self):
        body = "**Quick summary**\n\nNicole Kidman " + "word " * 700 + "\n\n## Frequently asked questions\n## Sources\n"
        good = ('---\ncelebrity: "Nicole Kidman"\nseo_title: "Nicole Kidman Practical Magic 2 Sequel Set for Release"\n'
                'seo_description: "Nicole Kidman confirms the Practical Magic 2 release date and what the long-awaited sequel means for fans."\n'
                'focus_keyword: "Nicole Kidman"\npermalink: "nicole-kidman-practical-magic-2"\n---\n' + body)
        bad = good.replace("seo_title", "x_title")
        with tempfile.TemporaryDirectory() as d:
            g, b = Path(d, "g.md"), Path(d, "b.md")
            g.write_text(good), b.write_text(bad)
            self.assertFalse([p for p in check_article.check(g) if "Rank Math" in p or "seo_" in p or "focus" in p or "permalink" in p])
            self.assertTrue(any("Rank Math fields missing" in p for p in check_article.check(b)))


if __name__ == "__main__":
    unittest.main()
