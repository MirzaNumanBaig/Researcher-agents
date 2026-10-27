"""The publisher copies each post's real featured image (also one set by hand in WordPress) into the article: python3 -m unittest discover tests"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parent.parent
ARTICLE = '---\ntitle: "T"\nstatus: sent\nwp_status: pending\nwp_synced: pending\nwp_id: 77\nwp_link: "https://x.test/?p=77"\n%s---\n\nbody\n'


class Mock(BaseHTTPRequestHandler):
    featured = 55
    media_fails = False

    def log_message(self, *a):
        pass

    def reply(self, code, body, headers=None):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_GET(self):
        path = urlparse(self.path).path
        if path.endswith("/posts") and "include=" in self.path:
            return self.reply(200, [{"id": 77, "status": "pending", "link": "https://x.test/?p=77", "featured_media": Mock.featured}])
        if path.endswith("/media"):
            if Mock.media_fails:
                return self.reply(500, {"code": "boom"})
            return self.reply(200, [{"id": 55, "source_url": "https://x.test/full.webp",
                                     "media_details": {"sizes": {"medium_large": {"source_url": "https://x.test/ml.webp"}}}}])
        self.reply(200, [], {"X-WP-Total": "0"})


def run(extra_front="", featured=55, media_fails=False):
    Mock.featured, Mock.media_fails = featured, media_fails
    server = HTTPServer(("127.0.0.1", 0), Mock)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "agents").mkdir()
        (root / "articles").mkdir()
        (root / "config.json").write_text("{}")
        (root / "agents" / "publish_wordpress.py").write_text((REPO / "agents" / "publish_wordpress.py").read_text())
        (root / "articles" / "a.md").write_text(ARTICLE % extra_front)
        env = dict(os.environ, WP_URL=f"http://127.0.0.1:{server.server_port}", WP_USER="u", WP_APP_PASSWORD="p")
        subprocess.run([sys.executable, str(root / "agents" / "publish_wordpress.py")], env=env, capture_output=True, text=True)
        out = (root / "articles" / "a.md").read_text()
    server.shutdown()
    server.server_close()
    return out


class ImageSync(unittest.TestCase):
    def test_featured_image_set_in_wordpress_reaches_the_article(self):
        out = run()
        self.assertIn('wp_image: "https://x.test/ml.webp"', out)  # dashboard-sized version, not the full file
        self.assertIn("wp_media_id: 55", out)

    def test_image_removed_in_wordpress_clears_the_preview_but_not_the_media_id(self):
        out = run('wp_image: "https://x.test/ml.webp"\nwp_media_id: 55\n', featured=0)
        self.assertIn('wp_image: ""', out)
        self.assertIn("wp_media_id: 55", out)

    def test_failed_media_lookup_changes_nothing(self):
        out = run('wp_image: "https://x.test/old.webp"\n', media_fails=True)
        self.assertIn('wp_image: "https://x.test/old.webp"', out)


if __name__ == "__main__":
    unittest.main()
