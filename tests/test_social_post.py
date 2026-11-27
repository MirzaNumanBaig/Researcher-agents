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


if __name__ == "__main__":
    unittest.main()
