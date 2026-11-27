import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents"))
import social_post as sp  # noqa: E402


def art(d, name, **kw):
    f = {"title": "A title", "description": "About it", "status": "sent", "wp_status": "publish", "wp_synced": "publish", "batch": "2026-11-28 09:00",
         "celebrity": "Isla Fisher", "wp_id": "1", "wp_link": "https://moduscarry.com/x/", "wp_image": "https://moduscarry.com/i.webp"}
    f.update(kw)
    (d / f"{name}.md").write_text("---\n" + "\n".join(f'{k}: "{v}"' for k, v in f.items() if v is not None) + "\n---\n\nBody")


class Social(unittest.TestCase):
    def test_which_posts_are_shared(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            art(d, "2026-11-28-09-00-a", wp_id="1")
            art(d, "2026-11-28-09-00-b", wp_id="2", wp_image="")  # no picture
            art(d, "2026-11-28-09-00-c", wp_id="3", wp_synced="pending")  # not live
            art(d, "2026-11-20-09-00-d", wp_id="4", batch="2026-11-20 09:00")  # older than the switch-on date
            art(d, "2026-11-28-09-00-e", wp_id="5", celebrity="Sai Pallavi")  # blocked
            art(d, "2026-11-28-09-00-f", wp_id="6")  # already shared
            cfg = {"social": {"enabled": True, "since": "2026-11-27"}, "blocked": ["Sai Pallavi"]}
            got = sp.candidates(cfg, {"shared": {"6": {}}, "log": []}, d)
            self.assertEqual([c[1] for c in got], ["1"])
            self.assertEqual(sp.candidates({"social": {"enabled": True, "since": ""}}, {"shared": {}, "log": []}, d), [])  # no since date = nothing

    def test_daily_cap_and_gap(self):
        now = datetime(2026, 11, 28, 12, 0, tzinfo=timezone.utc)
        cfg = {"social": {"daily_cap": 3, "min_gap_minutes": 10, "per_run": 2}}
        self.assertEqual(sp.allowed_now(cfg, {"log": []}, now), 2)
        self.assertEqual(sp.allowed_now(cfg, {"log": [(now - timedelta(minutes=5)).isoformat()]}, now), 0)  # too soon
        self.assertEqual(sp.allowed_now(cfg, {"log": [(now - timedelta(minutes=30)).isoformat()]}, now), 2)
        three = [(now - timedelta(minutes=m)).isoformat() for m in (300, 200, 100)]
        self.assertEqual(sp.allowed_now(cfg, {"log": three}, now), 0)  # cap reached
        two = three[:2]
        self.assertEqual(sp.allowed_now(cfg, {"log": two}, now), 1)

    def test_caption(self):
        self.assertEqual(sp.caption("T", "D", "https://x/"), "T\n\nD\n\nRead more: https://x/")
        self.assertEqual(sp.caption("T", "T", "https://x/"), "T\n\nRead more: https://x/")

    def test_pinterest_pin_has_board_title_link_and_image(self):
        calls = []

        def fake(method, path, key, body=None, headers=None):
            calls.append((method, path, body))
            if path.endswith("/pinterest-boards"):
                return {"boards": [{"id": "B1", "name": "Celebrity News"}, {"id": "B2", "name": "Movies"}]}
            return {"post": {"_id": "P1"}}

        sp.call = fake
        accts = [("pinterest", "ACC")]
        self.assertEqual(sp.pinterest_board("k", "ACC", ""), "B1")
        self.assertEqual(sp.pinterest_board("k", "ACC", "Movies"), "B2")
        self.assertEqual(sp.pinterest_board("k", "ACC", "B2"), "B2")
        sp.share("k", accts, {"pinterest_board": ""}, "T" * 150, "Desc", "https://moduscarry.com/x/", "https://moduscarry.com/i.webp", "9", "Desc")
        body = calls[-1][2]
        self.assertTrue(body["publishNow"])
        self.assertEqual(body["mediaItems"], [{"type": "image", "url": "https://moduscarry.com/i.webp"}])
        pd = body["platforms"][0]["platformSpecificData"]
        self.assertEqual(body["platforms"][0]["customContent"], "Desc")
        self.assertEqual((len(pd["title"]), pd["boardId"], pd["link"]), (100, "B1", "https://moduscarry.com/x/"))

    def test_threads_text_fits_500_and_ends_with_the_link(self):
        t = sp.threads_text("Headline", "word " * 200, "https://moduscarry.com/x/")
        self.assertLessEqual(len(t), 500)
        self.assertTrue(t.endswith("https://moduscarry.com/x/"))
        self.assertTrue(t.startswith("Headline"))
        self.assertEqual(sp.threads_text("Headline", "", "https://x/"), "Headline\n\nhttps://x/")

    def test_best_hours_gate(self):
        import social_analyst as sa
        slots = [{"day_of_week": 0, "hour": h, "avg_engagement": 10 - h % 5, "post_count": 3} for h in range(24)]
        res = sa.analyse({"pinterest": slots, "threads": slots[:2]})
        self.assertEqual(res["pinterest"]["status"], "ready")
        self.assertEqual(len(res["pinterest"]["hours"]), 12)
        self.assertEqual(res["threads"]["status"], "learning")  # too few posts: nothing is restricted
        times = {"platforms": res}
        hours = res["pinterest"]["hours"]
        out = [h for h in range(24) if h not in hours][0]
        self.assertTrue(sp.good_hour(datetime(2026, 11, 28, hours[0], 5, tzinfo=timezone.utc), times))
        self.assertFalse(sp.good_hour(datetime(2026, 11, 28, out, 5, tzinfo=timezone.utc), times))
        self.assertTrue(sp.good_hour(datetime(2026, 11, 28, out, 5, tzinfo=timezone.utc), {"platforms": {"pinterest": {"status": "learning"}}}))


if __name__ == "__main__":
    unittest.main()
