"""Tests for paper_dedup module."""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.paper_dedup import PaperDeduplicator


class TestPaperDeduplicator:
    def test_mark_and_is_seen(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({}, f)
            db_path = f.name

        dedup = PaperDeduplicator(db_path=db_path)
        assert not dedup.is_seen("paper123")
        dedup.mark_seen("paper123", "Test Paper")
        assert dedup.is_seen("paper123")

    def test_get_seen_ids(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({}, f)
            db_path = f.name

        dedup = PaperDeduplicator(db_path=db_path)
        dedup.mark_seen("p1", "Paper 1")
        dedup.mark_seen("p2", "Paper 2")
        seen = dedup.get_seen_ids()
        assert seen == {"p1", "p2"}

    def test_persistence(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump({}, f)
            db_path = f.name

        # First session
        dedup1 = PaperDeduplicator(db_path=db_path)
        dedup1.mark_seen("paper_a", "Paper A")
        dedup1.save()

        # Second session
        dedup2 = PaperDeduplicator(db_path=db_path)
        assert dedup2.is_seen("paper_a")
        assert not dedup2.is_seen("paper_b")

    def test_prune_90_day_window(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            old_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
            recent_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
            json.dump({
                "old_paper": {"title": "Old", "seen_at": old_date},
                "recent_paper": {"title": "Recent", "seen_at": recent_date},
            }, f)
            db_path = f.name

        dedup = PaperDeduplicator(db_path=db_path)
        dedup.prune(window_days=90)
        assert not dedup.is_seen("old_paper")
        assert dedup.is_seen("recent_paper")

    def test_corrupted_db_starts_fresh(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            f.write("not valid json{{{")
            db_path = f.name

        dedup = PaperDeduplicator(db_path=db_path)
        assert dedup._seen == {}

    def test_nonexistent_db_starts_fresh(self):
        dedup = PaperDeduplicator(db_path="/tmp/nonexistent_paper_db_12345.json")
        assert dedup._seen == {}
