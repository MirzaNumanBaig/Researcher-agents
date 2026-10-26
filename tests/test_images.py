"""Image-link extraction: python3 -m unittest discover tests"""
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents"))
import collect_news  # noqa: E402
import fetch_images  # noqa: E402


class PageImage(unittest.TestCase):
    def test_og_image_relative_and_escaped(self):
        page = '<head><meta property="og:image" content="/img/a.jpg?x=1&amp;y=2"></head>'
        self.assertEqual(fetch_images.page_image(page, "https://site.test/news/1"), "https://site.test/img/a.jpg?x=1&y=2")

    def test_falls_back_to_twitter_and_name_before_content(self):
        page = "<meta content='https://cdn.test/t.png' name='twitter:image'>"
        self.assertEqual(fetch_images.page_image(page, "https://site.test/"), "https://cdn.test/t.png")

    def test_none_and_non_http(self):
        self.assertEqual(fetch_images.page_image("<title>x</title>", "https://site.test/"), "")
        self.assertEqual(fetch_images.page_image('<meta property="og:image" content="data:image/png;base64,AA">', "https://site.test/"), "")


class FeedImage(unittest.TestCase):
    def item(self, xml):
        it = ET.fromstring(f'<item xmlns:media="http://search.yahoo.com/mrss/">{xml}</item>')
        return collect_news.feed_image(it, it.findtext("description"))

    def test_media_content(self):
        self.assertEqual(self.item('<media:content url="https://x.test/a.jpg" medium="image"/>'), "https://x.test/a.jpg")

    def test_enclosure_and_description_img(self):
        self.assertEqual(self.item('<enclosure url="https://x.test/e.jpg" type="image/jpeg"/>'), "https://x.test/e.jpg")
        self.assertEqual(self.item('<description>&lt;img src="https://x.test/d.jpg"&gt; text</description>'), "https://x.test/d.jpg")

    def test_video_enclosure_ignored(self):
        self.assertEqual(self.item('<enclosure url="https://x.test/v.mp4" type="video/mp4"/>'), "")


if __name__ == "__main__":
    unittest.main()
