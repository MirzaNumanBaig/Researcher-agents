"""Which articles get an AI image: python3 -m unittest discover tests"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents"))
import generate_images as gi  # noqa: E402

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


class WantsImage(unittest.TestCase):
    def test_approved_always(self):
        self.assertTrue(gi.wants_image("approved", "2026-10-01-10-00-x", False, NOW))

    def test_pending_only_when_the_run_will_send_it(self):
        self.assertFalse(gi.wants_image("pending", "2026-10-27-10-00-x", False, NOW))  # hourly sender: waits for a human
        self.assertTrue(gi.wants_image("pending", "2026-10-27-10-00-x", True, NOW))  # writer workflow: auto-approved next

    def test_sent_retries_recent_but_never_backfills_old(self):
        self.assertTrue(gi.wants_image("sent", "2026-10-26-18-00-x", False, NOW))
        self.assertFalse(gi.wants_image("sent", "2026-10-23-09-00-x", False, NOW))
        self.assertFalse(gi.wants_image("sent", "garbage", False, NOW))

    def test_other_statuses_never(self):
        for st in ("skipped", "rejected", "removed", "rewrite", ""):
            self.assertFalse(gi.wants_image(st, "2026-10-27-10-00-x", True, NOW), st)


if __name__ == "__main__":
    unittest.main()
