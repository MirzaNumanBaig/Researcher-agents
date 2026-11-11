"""Second photo source (Openverse), credited news pictures, hot-people roles and the movie money/verdict rules."""
import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "agents"))
import generate_images as gi  # noqa: E402
import movies  # noqa: E402
import openverse_photos as ov  # noqa: E402
import trending_people as tp  # noqa: E402


def item(**kw):
    base = {"id": "abc", "title": "Ryan Gosling", "foreign_landing_url": "https://www.flickr.com/photos/1/36034827222", "url": "https://live.staticflickr.com/x_b.jpg",
            "creator": "Gage Skidmore", "creator_url": "https://www.flickr.com/photos/1", "license": "by-sa", "license_version": "2.0",
            "license_url": "https://creativecommons.org/licenses/by-sa/2.0/", "source": "flickr", "filetype": "jpg", "width": 1024, "height": 683, "tags": [{"name": "actor"}]}
    base.update(kw)
    return base


class Openverse(unittest.TestCase):
    def test_good_photo_gets_credit_fields(self):
        p = ov.parse(item())
        self.assertEqual((p["license"], p["author"], p["source"], p["provider"]), ("CC BY-SA 2.0", "Gage Skidmore", "openverse", "Flickr"))
        self.assertEqual(p["file"], "Flickr:36034827222")

    def test_only_commercial_safe_licences(self):
        for lic in ("by-nc", "by-nd", "by-nc-sa", "nc-sampling+", ""):
            self.assertIsNone(ov.parse(item(license=lic)), lic)
        self.assertEqual(ov.parse(item(license="cc0"))["license"], "CC0 1.0")
        self.assertEqual(ov.parse(item(license="by", license_version="4.0"))["license"], "CC BY 4.0")

    def test_rejects_small_mature_non_jpeg_and_two_person_titles(self):
        self.assertIsNone(ov.parse(item(width=500, height=300)))
        self.assertIsNone(ov.parse(item(mature=True)))
        self.assertIsNone(ov.parse(item(filetype="png")))
        self.assertIsNone(ov.parse(item(title="Miley Cyrus and Liam Hemsworth")))
        self.assertIsNone(ov.parse(item(title="Ryan Gosling wax figure")))

    def test_title_must_name_the_person(self):
        p = ov.parse(item(title="Cannes 2018 red carpet"))
        self.assertFalse(ov.named("Ryan Gosling", p))
        self.assertTrue(ov.named("Ryan Gosling", ov.parse(item())))

    def test_blocklisted_photo_is_skipped(self):
        with mock.patch.object(ov.cp, "blocked", return_value={"Flickr:36034827222"}), mock.patch.object(ov, "search", return_value=[item()]):
            self.assertEqual(ov.refresh("Ryan Gosling"), [])

    def test_unverified_photo_is_never_kept(self):
        with mock.patch.object(ov.cp, "blocked", return_value=set()), mock.patch.object(ov, "search", return_value=[item()]), \
                mock.patch.object(ov, "check", return_value=(False, 0.0)):
            self.assertEqual(ov.refresh("Ryan Gosling"), [])
        with mock.patch.object(ov.cp, "blocked", return_value=set()), mock.patch.object(ov, "search", return_value=[item()]), \
                mock.patch.object(ov, "check", return_value=(True, 0.3)):
            self.assertEqual(len(ov.refresh("Ryan Gosling")), 1)


class Credits(unittest.TestCase):
    def test_used_photo_pages_tracks_any_source(self):
        credits = ['Photo: <a href="https://www.flickr.com/photos/1/2" rel="noopener">A</a>, x', 'Image: <a href="https://news.example/s">Outlet</a>']
        with mock.patch.object(gi.Path, "glob", return_value=[]):
            self.assertEqual(gi.used_photo_pages(), [])
        import re
        urls = [m.group(1) for c in credits for m in [re.match(r'Photo: <a href="(https?://[^"]+)"', c)] if m]
        self.assertEqual(urls, ["https://www.flickr.com/photos/1/2"])  # a news credit is not a pool photo

    def test_news_candidates_skip_google_thumbnails_and_logos(self):
        brief = {"stories": [{"outlets": [{"source": "A", "article_url": "https://a.example/x", "image": "https://lh3.googleusercontent.com/t.jpg"},
                                          {"source": "B", "article_url": "https://b.example/y", "image": "https://b.example/site-logo.png"},
                                          {"source": "C", "article_url": "https://c.example/z", "image": "https://c.example/photo.jpg"}]}]}
        front = 'batch: "2026-11-09 18:00"\ncelebrity: "Jacob Elordi"'
        with mock.patch.object(gi.Path, "read_text", return_value=json.dumps(brief)):
            self.assertEqual(gi.news_candidates(front), [("https://c.example/photo.jpg", "C", "https://c.example/z")])

    def test_news_photo_is_off_unless_enabled(self):
        with mock.patch.object(gi.Path, "read_text", return_value=json.dumps({"image_pipeline": {}})):
            self.assertIsNone(gi.news_photo('celebrity: "X"'))


class Hot(unittest.TestCase):
    def test_ids_come_from_wikipedia_with_redirects(self):
        data = {"query": {"normalized": [{"from": "Margot robbie", "to": "Margot Robbie"}], "redirects": [{"from": "Mags", "to": "Margot Robbie"}],
                          "pages": [{"title": "Margot Robbie", "pageprops": {"wikibase_item": "Q1924847"}}, {"title": "Main Page"}]}}
        with mock.patch.object(tp.rc, "fetch", return_value=data):
            self.assertEqual(tp.qids_for(["Margot_robbie", "Mags", "Main_Page"]), {"Margot_robbie": "Q1924847", "Mags": "Q1924847"})

    def test_people_query_groups_roles_and_flags_australians(self):
        def b(q, occ, au="0"):
            return {"p": {"value": "http://www.wikidata.org/entity/" + q}, "pLabel": {"value": "Margot Robbie"}, "pDescription": {"value": "Australian actress"},
                    "occ": {"value": "http://www.wikidata.org/entity/" + occ}, "au": {"value": au}}
        with mock.patch.object(tp, "qids_for", return_value={"Margot_Robbie": "Q1"}), mock.patch.object(tp.rc, "sparql", return_value=[b("Q1", "Q33999", "1"), b("Q1", "Q3282637", "1")]):
            p = tp.people_for(["Margot_Robbie"])["Q1"]
        self.assertEqual((p["roles"], p["australian"], p["page"]), (["actor", "producer"], True, "Margot_Robbie"))


class Money(unittest.TestCase):
    def test_money_parsing(self):
        self.assertEqual(movies.money("$150 million"), 150_000_000)
        self.assertEqual(movies.money("US$1.2 billion"), 1_200_000_000)
        self.assertEqual(movies.money("$12,345,678<ref>x</ref>"), 12_345_678)
        self.assertEqual(movies.money("{{US$|150|million}}"), 150_000_000)
        self.assertIsNone(movies.money("€40 million"))
        self.assertIsNone(movies.money(""))

    def test_scale_and_verdict(self):
        today = date(2026, 11, 11)
        self.assertEqual(movies.scale(200e6), "Blockbuster")
        self.assertEqual(movies.scale(5e6), "Indie / low budget")
        self.assertEqual(movies.verdict("2026-12-01", None, None, today), "Upcoming")
        self.assertEqual(movies.verdict("2026-11-05", 20e6, 50e6, today), "Too early")
        self.assertEqual(movies.verdict("2026-06-01", 300e6, 100e6, today), "Hit")
        self.assertEqual(movies.verdict("2026-06-01", 180e6, 100e6, today), "Modest")
        self.assertEqual(movies.verdict("2026-06-01", 90e6, 100e6, today), "Weak")
        self.assertEqual(movies.verdict("2026-06-01", None, 100e6, today), "No figures yet")


if __name__ == "__main__":
    unittest.main()
