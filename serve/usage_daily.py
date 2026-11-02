"""Today's counters for the Monitor: requests, tokens, average decode speed and peak concurrency.

The day is the computer's own calendar day and rolls over at midnight. The counters are kept in a
small JSON file, so a restart on the same day shows the day it counted, not zeros - the same idea
as the app host's Monitor counters (apps/host/server/monitor.mjs).
"""
import json
import os
from datetime import date


def default_usage_path(env=None):
    """Where the counters are kept: $STRATA_USAGE_FILE, else $STRATA_HOME/data/usage.json,
    else ~/.strata/data/usage.json (the folder a container keeps on its data volume)."""
    env = os.environ if env is None else env
    given = env.get("STRATA_USAGE_FILE")
    if given:
        return given
    home = env.get("STRATA_HOME") or os.path.join(os.path.expanduser("~"), ".strata")
    return os.path.join(home, "data", "usage.json")


class DailyUsage:
    """One day's counters. record() and note() are called under the server's status lock and
    stay in memory; flush() (from GET /metrics) is the only place that writes the file."""

    def __init__(self, path):
        self.path = path
        self._day = None
        self._dirty = False
        self.data = self._empty(date.today().isoformat())

    @staticmethod
    def _empty(day):
        return {"date": day, "requests": 0, "prompt_tokens": 0, "output_tokens": 0, "reused": 0,
                "decode_ms": 0.0, "usage_requests": 0, "avg_decode_tok_s": 0.0,
                "peak_running": 0, "peak_queued": 0}

    def _roll(self):
        today = date.today().isoformat()
        if self._day == today:
            return
        self._day = today
        self.data = self._empty(today)
        try:
            with open(self.path, encoding="utf-8") as handle:
                saved = json.load(handle)
            if saved.get("date") == today:
                self.data = {**self._empty(today), **saved}
        except (OSError, ValueError):
            pass
        self._dirty = False

    def record(self, prompt_tokens, output_tokens, reused=0, decode_ms=0.0, decode_tok_s=None):
        """One finished request. Speed is averaged over the requests that reported a decode time."""
        self._roll()
        d = self.data
        d["requests"] += 1
        d["prompt_tokens"] += prompt_tokens or 0
        d["output_tokens"] += output_tokens or 0
        d["reused"] += reused or 0
        d["decode_ms"] += decode_ms or 0.0
        if decode_tok_s:
            n = d["usage_requests"] = d["usage_requests"] + 1
            d["avg_decode_tok_s"] = round((d["avg_decode_tok_s"] * (n - 1) + decode_tok_s) / n, 1)
        self._dirty = True

    def note(self, running, queued):
        """The highest concurrency seen today; a quieter minute never lowers it."""
        self._roll()
        d = self.data
        if running is not None and running > d["peak_running"]:
            d["peak_running"] = running
            self._dirty = True
        if queued is not None and queued > d["peak_queued"]:
            d["peak_queued"] = queued
            self._dirty = True

    def snapshot(self):
        self._roll()
        return dict(self.data)

    def flush(self):
        if not self._dirty:
            return
        self._dirty = False
        try:
            folder = os.path.dirname(self.path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(self.data, handle)
            os.replace(tmp, self.path)
        except OSError:
            pass                                   # a read-only place only costs the read-back after a restart
