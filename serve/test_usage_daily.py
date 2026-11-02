"""Today's counters (the Monitor's Today card): accumulation, read-back, rollover and peaks.

    python -m unittest serve.test_usage_daily -v
"""
import json
import os
import tempfile
import unittest
from datetime import date, timedelta

from serve.usage_daily import DailyUsage, default_usage_path


class DailyUsageCounters(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "usage.json")

    def test_requests_and_speed_accumulate(self):
        d = DailyUsage(self.path)
        d.record(100, 40, reused=25, decode_ms=1000.0, decode_tok_s=40.0)
        d.record(50, 10, reused=0, decode_ms=500.0, decode_tok_s=20.0)
        d.record(None, None)                              # a request with no usage is still a request
        snap = d.snapshot()
        self.assertEqual(snap["date"], date.today().isoformat())
        self.assertEqual(snap["requests"], 3)
        self.assertEqual(snap["prompt_tokens"], 150)
        self.assertEqual(snap["output_tokens"], 50)
        self.assertEqual(snap["reused"], 25)
        self.assertEqual(snap["usage_requests"], 2)
        self.assertEqual(snap["avg_decode_tok_s"], 30.0)  # the mean of the two reported speeds
        self.assertEqual(snap["peak_running"], 0)

    def test_peaks_keep_the_highest_of_the_day(self):
        d = DailyUsage(self.path)
        d.note(3, 1)
        d.note(1, 0)
        d.note(2, 4)
        snap = d.snapshot()
        self.assertEqual(snap["peak_running"], 3)
        self.assertEqual(snap["peak_queued"], 4)

    def test_flush_then_restart_keeps_the_day(self):
        d = DailyUsage(self.path)
        d.record(100, 40, reused=25, decode_ms=1000.0, decode_tok_s=40.0)
        d.note(2, 1)
        d.flush()
        with open(self.path, encoding="utf-8") as handle:
            saved = json.load(handle)
        self.assertEqual(saved["requests"], 1)
        d2 = DailyUsage(self.path)                        # the host starts again the same day
        self.assertEqual(d2.snapshot()["requests"], 1)
        self.assertEqual(d2.snapshot()["output_tokens"], 40)
        self.assertEqual(d2.snapshot()["peak_running"], 2)

    def test_the_file_of_an_earlier_day_is_not_mixed_in(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump({"date": yesterday, "requests": 9, "prompt_tokens": 900, "output_tokens": 90,
                       "reused": 0, "decode_ms": 0.0, "usage_requests": 0, "avg_decode_tok_s": 0.0,
                       "peak_running": 9, "peak_queued": 9}, handle)
        d = DailyUsage(self.path)
        snap = d.snapshot()
        self.assertEqual(snap["date"], date.today().isoformat())
        self.assertEqual(snap["requests"], 0)
        self.assertEqual(snap["peak_running"], 0)

    def test_a_midnight_record_rolls_the_day(self):
        d = DailyUsage(self.path)
        d.record(10, 5, decode_ms=100.0, decode_tok_s=50.0)
        d._day = (date.today() - timedelta(days=1)).isoformat()   # as if the clock passed midnight
        d.record(1, 1)
        snap = d.snapshot()
        self.assertEqual(snap["date"], date.today().isoformat())
        self.assertEqual(snap["requests"], 1)
        self.assertEqual(snap["avg_decode_tok_s"], 0.0)


class UsagePath(unittest.TestCase):
    def test_the_file_follows_the_data_folder_of_the_machine(self):
        self.assertEqual(default_usage_path({"STRATA_USAGE_FILE": "/data/usage.json"}), "/data/usage.json")
        self.assertEqual(default_usage_path({"STRATA_HOME": "/data/home/.strata"}),
                         os.path.join("/data/home/.strata", "data", "usage.json"))
        self.assertTrue(default_usage_path({}).endswith(os.path.join("data", "usage.json")))


if __name__ == "__main__":
    unittest.main()
