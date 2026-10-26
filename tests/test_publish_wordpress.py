"""Runs agents/publish_wordpress.py against a mock WordPress REST API (stdlib only): python3 -m unittest discover tests"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO = Path(__file__).resolve().parent.parent
ARTICLE = '---\ntitle: "Test"\nstatus: approved\nwp_status: draft\ntags: ["Zz Late Tag", "Brand New"]\ncategories: ["News"]\n---\n\nHello **world**.\n'


class Mock(BaseHTTPRequestHandler):
    tags = {f"Tag {i:03}": i for i in range(1, 123)}  # 122 tags: more than one page
    tags["Zz Late Tag"] = 500
    posts = []
    reject_taxonomy = False

    def log_message(self, *a):
        pass

    def send(self, code, body, headers=None):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path.endswith("/tags"):
            names = sorted(self.tags.items())
            per, page = int(q.get("per_page", ["10"])[0]), int(q.get("page", ["1"])[0])
            return self.send(200, [{"id": i, "name": n} for n, i in names[(page - 1) * per:page * per]])
        if u.path.endswith("/categories"):
            return self.send(200, [{"id": 9, "name": "News"}])
        self.send(200, [], {"X-WP-Total": "0"})

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.endswith("/tags"):
            if data["name"] in self.tags:
                return self.send(400, {"code": "term_exists", "message": "A term with the name provided already exists.",
                                       "data": {"status": 400, "term_id": self.tags[data["name"]]}})
            self.tags[data["name"]] = 1000 + len(self.tags)
            return self.send(201, {"id": self.tags[data["name"]]})
        if self.reject_taxonomy and "tags" in data:
            return self.send(400, {"code": "rest_invalid_param", "message": "Invalid parameter(s): tags"})
        self.posts.append(data)
        self.send(201, {"id": 77, "link": "https://example.test/?p=77"})


def run_publisher(reject_taxonomy):
    Mock.posts, Mock.reject_taxonomy = [], reject_taxonomy
    server = HTTPServer(("127.0.0.1", 0), Mock)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "agents").mkdir()
        (root / "articles").mkdir()
        (root / "config.json").write_text("{}")
        (root / "agents" / "publish_wordpress.py").write_text((REPO / "agents" / "publish_wordpress.py").read_text())
        (root / "articles" / "a.md").write_text(ARTICLE)
        env = dict(os.environ, WP_URL=f"http://127.0.0.1:{server.server_port}", WP_USER="u", WP_APP_PASSWORD="p")
        res = subprocess.run([sys.executable, str(root / "agents" / "publish_wordpress.py")], env=env, capture_output=True, text=True)
        out = (root / "articles" / "a.md").read_text()
    server.shutdown()
    return res, out


class PublishTests(unittest.TestCase):
    def test_existing_tag_beyond_first_page_is_reused(self):
        res, out = run_publisher(False)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn(500, Mock.posts[0]["tags"])  # found on page 2, not re-created
        self.assertIn("status: sent", out)

    def test_rejected_taxonomy_does_not_block_the_article(self):
        res, out = run_publisher(True)
        self.assertIn("status: sent", out)
        self.assertNotIn("tags", Mock.posts[0])


if __name__ == "__main__":
    unittest.main()
