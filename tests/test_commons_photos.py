"""Open-licence photo pool: licence rules, parsing, ranking, topic-aware pick with reuse, and generate_images with AI switched off."""
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

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "agents"))
import commons_photos as cp  # noqa: E402
import generate_images as gi  # noqa: E402


def page(title="File:Keanu Reeves at the Venice Film Festival.jpg", lic="CC BY-SA 4.0", w=3000, h=2000, mime="image/jpeg", desc="Keanu Reeves in 2024", **meta):
    m = {"LicenseShortName": {"value": lic}, "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"},
         "Artist": {"value": '<a href="//commons.wikimedia.org/wiki/User:Jane">Jane Doe</a>'}, "ImageDescription": {"value": desc},
         "DateTimeOriginal": {"value": "2024-09-03"}, "Categories": {"value": "Keanu Reeves in 2024|Featured pictures of people"}}
    m.update({k: {"value": v} for k, v in meta.items()})
    return {"title": title, "imageinfo": [{"width": w, "height": h, "mime": mime, "url": "https://upload.wikimedia.org/x.jpg", "thumburl": "https://thumb.wikimedia.org/x-1920.jpg",
                                           "descriptionurl": "https://commons.wikimedia.org/wiki/" + title.replace(" ", "_"), "extmetadata": m}]}


class Licences(unittest.TestCase):
    def test_commercial_safe_licences_only(self):
        for ok in ("CC BY 2.0", "CC BY-SA 4.0", "CC BY-SA 3.0", "CC0", "Public domain", "PD-USGov", "CC BY 4.0"):
            self.assertTrue(cp.allowed_license(ok), ok)
        for bad in ("CC BY-NC 2.0", "CC BY-ND 2.0", "CC BY-NC-SA 4.0", "GFDL", "Fair use", "Copyrighted free use", "", "All rights reserved"):
            self.assertFalse(cp.allowed_license(bad), bad)

    def test_parse_accepts_a_good_photo_and_extracts_credit_fields(self):
        p = cp.parse_photo(page(), "Category:Keanu Reeves")
        self.assertEqual((p["license"], p["author"], p["date"]), ("CC BY-SA 4.0", "Jane Doe", "2024-09-03"))
        self.assertEqual(p["author_url"], "https://commons.wikimedia.org/wiki/User:Jane")
        self.assertEqual(p["thumb"], "https://thumb.wikimedia.org/x-1920.jpg")
        self.assertIn("Jane Doe, CC BY-SA 4.0, via Wikimedia Commons", p["credit"])

    def test_parse_rejects_unusable_files(self):
        self.assertIsNone(cp.parse_photo(page(lic="CC BY-NC 2.0")))
        self.assertIsNone(cp.parse_photo(page(mime="image/png")))
        self.assertIsNone(cp.parse_photo(page(w=800, h=600)))  # too small to fill a 1600 px image
        self.assertIsNone(cp.parse_photo(page(title="File:Keanu Reeves poster.jpg")))
        self.assertIsNone(cp.parse_photo(page(title="File:Keanu Reeves wax figure.jpg")))
        self.assertIsNone(cp.parse_photo(page(NonFree="true")))
        self.assertIsNone(cp.parse_photo({"title": "File:x.jpg"}))


class Ranking(unittest.TestCase):
    def test_recent_large_landscape_rated_photos_rank_higher(self):
        base = cp.parse_photo(page())
        old = cp.parse_photo(page(DateTimeOriginal="2009-01-01", Categories="Keanu Reeves"))
        portrait = cp.parse_photo(page(w=2000, h=3000))
        small = cp.parse_photo(page(w=1300, h=800))
        s = lambda p: cp.score(p, "Keanu Reeves", 2026)  # noqa: E731
        self.assertGreater(s(base), s(old))
        self.assertGreater(s(base), s(portrait))
        self.assertGreater(s(base), s(small))

    def test_a_photo_described_as_this_person_ranks_above_an_unnamed_one(self):
        named = cp.parse_photo(page(title="File:Keanu Reeves 2024.jpg", desc="Keanu Reeves at the premiere"))
        unnamed = cp.parse_photo(page(title="File:IMG_4412.jpg", desc="A man on a red carpet"))
        self.assertGreater(cp.score(named, "Keanu Reeves", 2026), cp.score(unnamed, "Keanu Reeves", 2026))


PHOTOS = [{"page": f"https://commons.wikimedia.org/wiki/File:{n}.jpg", "file": f"File:{n}.jpg", "description": d, "category": "Category:Keanu Reeves"}
          for n, d in (("A", "at a press event"), ("B", "at the Cannes Film Festival premiere"), ("C", "in 2024"))]


class Pick(unittest.TestCase):
    def test_unused_first_in_ranked_order(self):
        self.assertEqual(gi.pick_photo(PHOTOS, [])["file"], "File:A.jpg")
        self.assertEqual(gi.pick_photo(PHOTOS, [PHOTOS[0]["page"]])["file"], "File:B.jpg")

    def test_the_headline_can_choose_a_better_matching_photo(self):
        self.assertEqual(gi.pick_photo(PHOTOS, [], "Keanu Reeves returns to Cannes for a new film premiere")["file"], "File:B.jpg")

    def test_when_all_are_used_none_by_default_or_the_least_recently_used_with_reuse(self):
        used = [PHOTOS[1]["page"], PHOTOS[2]["page"], PHOTOS[0]["page"]]  # oldest use first
        self.assertIsNone(gi.pick_photo(PHOTOS, used))
        self.assertEqual(gi.pick_photo(PHOTOS, used, reuse=True)["file"], "File:B.jpg")
        self.assertIsNone(gi.pick_photo([], [], reuse=True))

    def test_used_order_is_oldest_first_and_a_reused_photo_moves_to_the_end(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "articles").mkdir()
            for name, page_ in (("2026-01-01-00-00-a", "P1"), ("2026-01-02-00-00-b", "P2"), ("2026-01-03-00-00-c", "P1")):
                (root / "articles" / f"{name}.md").write_text(f'---\ntitle: "t"\nimage_credit: "Photo: <a href=\\"https://commons.wikimedia.org/wiki/File:{page_}.jpg\\">x</a>"\n---\n\nbody\n')
            old, gi.ROOT = gi.ROOT, root
            try:
                self.assertEqual([u.rsplit(":", 1)[1] for u in gi.used_photo_pages()], ["P2.jpg", "P1.jpg"])
            finally:
                gi.ROOT = old


class Serve(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        from PIL import Image
        img = Image.linear_gradient("L").resize((1920, 1280))
        buf = io.BytesIO()
        Image.merge("RGB", (img, img.transpose(Image.FLIP_LEFT_RIGHT), img)).save(buf, "JPEG")
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.end_headers()
        self.wfile.write(buf.getvalue())


class ImageStepWithAiOff(unittest.TestCase):
    def run_step(self, config, sheet):
        srv = HTTPServer(("127.0.0.1", 0), Serve)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "articles").mkdir()
            (root / "data").mkdir()
            subprocess.run(["cp", "-r", str(REPO / "agents"), str(root / "agents")], check=True)
            (root / "config.json").write_text(json.dumps(config))
            for entry in sheet.get("Keanu Reeves", {}).get("photos", []):
                entry["thumb"] = f"http://127.0.0.1:{srv.server_port}/photo.jpg"
            (root / "data" / "character-sheet.json").write_text(json.dumps(sheet))
            (root / "articles" / "2099-01-01-00-00-keanu-reeves.md").write_text(
                '---\ntitle: "Keanu Reeves returns"\nstatus: approved\nwp_status: pending\ncelebrity: "Keanu Reeves"\n---\n\nBody.\n')
            env = {k: v for k, v in os.environ.items() if not k.startswith("CF_")}
            r = subprocess.run([sys.executable, str(root / "agents" / "generate_images.py"), "--max", "5"], env=env, capture_output=True, text=True)
            front = (root / "articles" / "2099-01-01-00-00-keanu-reeves.md").read_text()
            has_img = (root / "articles" / "images" / "2099-01-01-00-00-keanu-reeves.webp").exists()
        srv.shutdown()
        return r, front, has_img

    SHEET = {"Keanu Reeves": {"status": "ok", "photos": [{"page": "https://commons.wikimedia.org/wiki/File:K.jpg", "file": "File:K.jpg", "url": "x", "thumb": "x",
                                                         "license": "CC BY-SA 4.0", "license_url": "https://creativecommons.org/licenses/by-sa/4.0",
                                                         "author": "Jane Doe", "description": "Keanu Reeves in 2024"}]}}

    def test_real_photo_is_used_without_any_cloudflare_secrets_and_with_ai_off(self):
        r, front, has_img = self.run_step({"ai_images": False, "celebrities": ["Keanu Reeves"], "image_pipeline": {"real_photos": True}}, json.loads(json.dumps(self.SHEET)))
        self.assertIn("1 image(s) created", r.stdout, r.stderr)
        self.assertTrue(has_img)
        self.assertIn("image_credit:", front)
        self.assertIn("(cropped)", front)
        self.assertIn("Jane Doe", front)

    def test_no_photo_and_ai_off_publishes_without_an_image_and_without_error(self):
        r, front, has_img = self.run_step({"ai_images": False, "celebrities": ["Keanu Reeves"], "image_pipeline": {"real_photos": True}},
                                          {"Keanu Reeves": {"status": "no_free_photo", "photos": []}})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("0 image(s) created, 0 failed", r.stdout)
        self.assertFalse(has_img)

    def test_everything_off_does_nothing(self):
        r, front, has_img = self.run_step({"ai_images": False, "celebrities": ["Keanu Reeves"], "image_pipeline": {}}, self.SHEET)
        self.assertIn("no images generated", r.stdout)
        self.assertFalse(has_img)


if __name__ == "__main__":
    unittest.main()
