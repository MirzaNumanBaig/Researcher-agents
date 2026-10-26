"""30-day cleanup rules: python3 -m unittest discover tests"""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents"))
import collect_news  # noqa: E402

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(days=30)


class Expired(unittest.TestCase):
    def test_by_published_date(self):
        self.assertTrue(collect_news.expired({"published": (NOW - timedelta(days=31)).isoformat()}, CUTOFF))
        self.assertFalse(collect_news.expired({"published": (NOW - timedelta(days=29)).isoformat()}, CUTOFF))

    def test_falls_back_to_found_time(self):
        self.assertTrue(collect_news.expired({"published": None, "found": (NOW - timedelta(days=40)).isoformat()}, CUTOFF))

    def test_undated_is_kept(self):
        self.assertFalse(collect_news.expired({}, CUTOFF))


class PruneBriefs(unittest.TestCase):
    def test_only_folders_older_than_cutoff_are_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("2026-09-01-10-00", "2026-10-20-10-00", "not-a-date"):
                (root / "briefs" / name).mkdir(parents=True)
                (root / "briefs" / name / "x.json").write_text("{}")
            old, collect_news.ROOT = collect_news.ROOT, root
            try:
                self.assertEqual(collect_news.prune_briefs(CUTOFF), 1)
            finally:
                collect_news.ROOT = old
            left = sorted(p.name for p in (root / "briefs").iterdir())
            self.assertEqual(left, ["2026-10-20-10-00", "not-a-date"])


if __name__ == "__main__":
    unittest.main()
