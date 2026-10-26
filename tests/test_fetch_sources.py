"""Source-page reading: python3 -m unittest discover tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents"))
import fetch_sources as fs  # noqa: E402


class StructuredText(unittest.TestCase):
    def test_article_body_from_json_ld_graph(self):
        page = '<script type="application/ld+json">{"@graph":[{"@type":"NewsArticle","articleBody":"<p>Full &amp; real text.</p>"}]}</script>'
        self.assertEqual(fs.structured_text(page), "Full & real text.")

    def test_bad_json_and_missing_body(self):
        self.assertEqual(fs.structured_text('<script type="application/ld+json">{oops</script>'), "")
        self.assertEqual(fs.structured_text("<p>nothing</p>"), "")


class Walls(unittest.TestCase):
    def test_cookie_wall_titles(self):
        self.assertTrue(fs.COOKIE_WALL.search("No Cookies | The Cairns Post"))
        self.assertTrue(fs.COOKIE_WALL.search("We value your privacy"))
        self.assertFalse(fs.COOKIE_WALL.search("Hugh Jackman wins award for cooking show"))

    def test_non_article_paths(self):
        for path in ("/pictures/abc/hugh-jackman/", "/es/list/ls009/mediaviewer/rm1/", "/gallery/x"):
            self.assertTrue(fs.NOT_ARTICLE.search(path), path)
        self.assertFalse(fs.NOT_ARTICLE.search("/entertainment/news-story/abc"))


if __name__ == "__main__":
    unittest.main()
