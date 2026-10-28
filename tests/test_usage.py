"""Usage tracking for the dashboard: Claude token records from the writer job, neuron summaries, and the built page: python3 -m unittest discover tests"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "agents"))
import record_usage as ru  # noqa: E402
import usage_stats as us  # noqa: E402

RESULT = {"type": "result", "subtype": "success", "is_error": False, "num_turns": 12, "duration_ms": 81400, "total_cost_usd": 0.41234,
          "usage": {"input_tokens": 40, "output_tokens": 6100, "cache_read_input_tokens": 210000, "cache_creation_input_tokens": 18000}}
LOG = [{"type": "system", "subtype": "init"}, {"type": "assistant", "message": {"id": "m1", "usage": {"input_tokens": 5, "output_tokens": 100}}}, RESULT]
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
day = lambda n: (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")  # noqa: E731


class ParseExecutionFile(unittest.TestCase):
    def test_result_message_gives_the_exact_counts(self):
        self.assertEqual(ru.parse_execution(json.dumps(LOG)), {"ok": True, "input_tokens": 40, "output_tokens": 6100, "cache_read_tokens": 210000,
                                                              "cache_write_tokens": 18000, "turns": 12, "seconds": 81, "cost_usd": 0.4123})

    def test_json_lines_and_a_single_object_are_accepted(self):
        self.assertEqual(ru.parse_execution("\n".join(json.dumps(m) for m in LOG))["output_tokens"], 6100)
        self.assertEqual(ru.parse_execution(json.dumps(RESULT))["turns"], 12)

    def test_a_cut_off_run_without_a_result_is_added_up_per_message_and_marked_not_ok(self):
        log = [{"type": "assistant", "message": {"id": "a", "usage": {"input_tokens": 3, "output_tokens": 10}}},
               {"type": "assistant", "message": {"id": "a", "usage": {"input_tokens": 3, "output_tokens": 50}}},  # the same message streamed again: last count wins
               {"type": "assistant", "message": {"id": "b", "usage": {"input_tokens": 4, "output_tokens": 70, "cache_read_input_tokens": 900}}}]
        r = ru.parse_execution(json.dumps(log))
        self.assertEqual((r["ok"], r["input_tokens"], r["output_tokens"], r["cache_read_tokens"], r["turns"]), (False, 7, 120, 900, 2))

    def test_failed_result_is_not_ok(self):
        self.assertFalse(ru.parse_execution(json.dumps([dict(RESULT, subtype="error_max_turns")]))["ok"])
        self.assertFalse(ru.parse_execution(json.dumps([dict(RESULT, is_error=True)]))["ok"])

    def test_garbage_empty_or_usage_free_files_give_nothing(self):
        for text in ("", "not json at all", "[]", json.dumps([{"type": "system"}]), None):
            self.assertIsNone(ru.parse_execution(text))


class RecordCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "data").mkdir()
        self.log = self.tmp / "exec.json"
        self.log.write_text(json.dumps(LOG))

    def run_cmd(self, *args):
        return subprocess.run([sys.executable, str(REPO / "agents" / "record_usage.py"), *args], capture_output=True, text=True,
                              env={**os.environ, "PYTHONPATH": ""}, cwd=self.tmp)

    def test_cli_appends_one_record_per_writer_that_ran(self):
        shutil.copytree(REPO / "agents", self.tmp / "agents")  # the script writes into <repo>/data of its own checkout
        r = subprocess.run([sys.executable, str(self.tmp / "agents" / "record_usage.py"), "--celebrity", "Nicole Kidman", "--batch", "2026-10-28 09:00",
                            "--article", "articles/2026-10-28-09-00-nicole-kidman.md", f"claude1={self.log}", "claude2=", f"claude3={self.tmp / 'missing.json'}"],
                           capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "recorded 1 writer run(s)"), r.stderr)
        rec = json.loads((self.tmp / "data" / "claude_usage.json").read_text())["records"]
        self.assertEqual(len(rec), 1)
        self.assertEqual((rec[0]["celebrity"], rec[0]["writer"], rec[0]["article"], rec[0]["output_tokens"], rec[0]["date"]),
                         ("Nicole Kidman", "claude1", "2026-10-28-09-00-nicole-kidman.md", 6100, TODAY))

    def test_nothing_to_record_changes_nothing_and_never_fails_the_job(self):
        shutil.copytree(REPO / "agents", self.tmp / "agents")
        r = subprocess.run([sys.executable, str(self.tmp / "agents" / "record_usage.py"), "--celebrity", "X", "claude1=", "claude2="], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertFalse((self.tmp / "data" / "claude_usage.json").exists())

    def test_the_file_keeps_only_the_latest_records(self):
        path = self.tmp / "data" / "claude_usage.json"
        ru.append([{"n": i} for i in range(ru.KEEP + 5)], path)
        recs = json.loads(path.read_text())["records"]
        self.assertEqual((len(recs), recs[0]["n"], recs[-1]["n"]), (ru.KEEP, 5, ru.KEEP + 4))


class Summaries(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "data").mkdir()
        (self.tmp / "articles" / "image-meta").mkdir(parents=True)

    def rec(self, n, writer="claude1", out=1000, celeb="A", batch="b"):
        return {"date": day(n), "batch": batch, "celebrity": celeb, "writer": writer, "input_tokens": 10, "output_tokens": out, "cache_read_tokens": 500,
                "cache_write_tokens": 0, "turns": 5, "cost_usd": 0.25, "time": f"{day(n)}T10:00:00+00:00", "article": "x.md", "ok": True}

    def test_claude_totals_windows_writers_and_days(self):
        (self.tmp / "data" / "claude_usage.json").write_text(json.dumps({"records": [
            self.rec(0, out=1000, celeb="A"), self.rec(0, "claude2", out=2000, celeb="B"), self.rec(3, out=500), self.rec(20, out=100), self.rec(40, out=9999)]}))
        c = us.claude_summary(self.tmp)
        self.assertEqual((c["today"]["tokens"], c["today"]["articles"], c["today"]["runs"]), (3020, 2, 2))
        self.assertEqual(c["week"]["tokens"], 3020 + 510)
        self.assertEqual(c["month"]["tokens"], 3020 + 510 + 110)  # the 40-day-old record is outside the 30 days
        self.assertEqual(c["month"]["cost_usd"], 1.0)
        self.assertEqual({w: v["runs"] for w, v in c["writers"].items()}, {"claude1": 3, "claude2": 1})
        self.assertEqual(len(c["days"]), 14)
        self.assertEqual((c["days"][-1]["date"], c["days"][-1]["tokens"]), (day(0), 3020))
        self.assertEqual(len(c["recent"]), 5)
        self.assertEqual(c["recent"][0]["time"][:10], day(40))  # newest first: the last record written

    def test_no_data_says_so(self):
        c = us.claude_summary(self.tmp)
        self.assertFalse(c["has_data"])
        self.assertEqual((c["today"]["tokens"], c["recent"], c["writers"]), (0, [], {}))
        n = us.neuron_summary(self.tmp, {})
        self.assertEqual((n["has_data"], n["budget"], n["accounts"]), (False, 9000, [{"slot": 1, "used": 0, "spent": False}]))

    def test_neurons_per_account_budget_and_history(self):
        (self.tmp / "articles" / "image-meta" / "_usage.json").write_text(json.dumps({
            "date": TODAY, "images": 31, "neurons": {"1": 7650, "2": 2100},
            "history": {day(2): {"neurons": {"1": 3000}, "images": 20}, day(1): {"neurons": {"1": 4000, "2": 500}, "images": 30}}}))
        n = us.neuron_summary(self.tmp, {"image_pipeline": {"neuron_budget": 9000, "image_model": "@cf/black-forest-labs/flux-1-schnell"}})
        self.assertEqual(n["accounts"], [{"slot": 1, "used": 7650, "spent": False}, {"slot": 2, "used": 2100, "spent": False}])
        self.assertEqual((n["budget"], n["images_today"], n["free_limit"], n["model"]), (9000, 31, 10000, "@cf/black-forest-labs/flux-1-schnell"))
        self.assertEqual([(h["date"], h["total"]) for h in n["history"]], [(day(2), 3000), (day(1), 4500), (TODAY, 9750)])

    def test_yesterdays_file_is_history_not_todays_usage(self):
        (self.tmp / "articles" / "image-meta" / "_usage.json").write_text(json.dumps({"date": day(1), "images": 5, "neurons": {"1": 800}}))
        n = us.neuron_summary(self.tmp, {})
        self.assertEqual(n["accounts"], [{"slot": 1, "used": 0, "spent": False}])
        self.assertEqual(n["history"], [{"date": day(1), "total": 800, "images": 5}])

    def test_an_unreadable_file_does_not_break_the_dashboard(self):
        (self.tmp / "data" / "claude_usage.json").write_text("{broken")
        (self.tmp / "articles" / "image-meta" / "_usage.json").write_text("[1,2")
        self.assertFalse(us.claude_summary(self.tmp)["has_data"])
        self.assertFalse(us.neuron_summary(self.tmp, {})["has_data"])


class SpentAccounts(unittest.TestCase):
    def test_an_account_cloudflare_stopped_is_saved_by_slot_and_shown_as_full(self):
        import cf_accounts
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        env = {"IMG_META_DIR": str(tmp / "articles" / "image-meta"), "CF_ACCOUNT_ID": "acct-one", "CF_API_TOKEN": "t1", "CF_ACCOUNT_ID_2": "acct-two", "CF_API_TOKEN_2": "t2"}
        with unittest.mock.patch.dict(os.environ, env):
            cf_accounts.reset()
            cf_accounts.mark_spent("acct-one")
            cf_accounts.mark_spent("acct-one")  # twice: still one entry
            cf_accounts.record("acct-two", 4220)
            self.addCleanup(cf_accounts.reset)
        saved = json.loads((tmp / "articles" / "image-meta" / "_usage.json").read_text())
        self.assertEqual((saved["spent"], saved["neurons"]), (["1"], {"2": 4220}))
        self.assertNotIn("acct-one", json.dumps(saved))  # slot numbers only, never an account id
        n = us.neuron_summary(tmp, {})
        self.assertEqual(n["accounts"], [{"slot": 1, "used": 10000, "spent": True}, {"slot": 2, "used": 4220, "spent": False}])


class BuiltDashboard(unittest.TestCase):
    def test_the_page_carries_both_usage_blocks_and_a_usage_tab(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        for name in ("agents", "config.json"):
            src = REPO / name
            shutil.copytree(src, tmp / name) if src.is_dir() else shutil.copy(src, tmp / name)
        (tmp / "data").mkdir()
        (tmp / "data" / "leads.json").write_text("[]")
        (tmp / "articles" / "image-meta").mkdir(parents=True)
        (tmp / "articles" / "image-meta" / "_usage.json").write_text(json.dumps({"date": TODAY, "images": 3, "neurons": {"1": 450}}))
        (tmp / "data" / "claude_usage.json").write_text(json.dumps({"records": [{"date": TODAY, "celebrity": "A", "batch": "b", "writer": "claude1", "input_tokens": 1,
                                                                                    "output_tokens": 2, "cache_read_tokens": 3, "turns": 1, "cost_usd": 0.1, "time": TODAY + "T00:00:00+00:00"}]}))
        r = subprocess.run([sys.executable, str(tmp / "agents" / "build_dashboard.py")], capture_output=True, text=True, cwd=tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        page = (tmp / "docs" / "index.html").read_text()
        data = json.loads(re.search(r"const D=(\{.*\}),REPO=D\.repo;", page).group(1).replace("<\\/", "</"))
        self.assertEqual(data["neurons"]["accounts"], [{"slot": 1, "used": 450, "spent": False}])
        self.assertEqual(data["claude_usage"]["today"]["tokens"], 3)
        self.assertIn('id="v-usage"', page)
        self.assertIn("usageView", page)
        self.assertRegex(page, r'<main class="wrap">\s*<section class="health usagebar" id="usagebar"')  # the strip sits first, right under the header
        self.assertIn("function usageBar()", page)


if __name__ == "__main__":
    unittest.main()
