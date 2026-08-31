"""Unit tests for the PulseGrid ingest endpoint helpers.

Pure tests (no network, no live DB): payload normalization and dedup-window
logic. Run: uv run --with pytest pytest tests/test_ingest.py -q
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from routers.ingest import (  # noqa: E402
    IngestPayload,
    TriageResult,
    check_dedup,
    normalize_payload,
)

# check_dedup only reads os.getenv and touches db.get — with a dedup_key of
# None it short-circuits before any DB access, so db=None is safe there.
DB = None


class TestNormalizePayload(unittest.TestCase):
    def test_source_prefixed_title(self):
        p = IngestPayload(source="alertmanager", title="High error rate", description="5xx spike", logs="log line")
        title, description, logs = normalize_payload(p)
        self.assertEqual(title, "[alertmanager] High error rate")
        self.assertIn("5xx spike", description)
        self.assertEqual(logs, "log line")

    def test_labels_rendered_into_description(self):
        p = IngestPayload(
            source="reconciliation",
            title="Sync mismatch",
            labels={"alertname": "SilentSync", "instance": "crm:8000"},
        )
        _, description, _ = normalize_payload(p)
        self.assertIn("Labels:", description)
        self.assertIn("alertname=SilentSync", description)
        self.assertIn("instance=crm:8000", description)

    def test_triage_result_included(self):
        p = IngestPayload(
            source="newman",
            title="Health check failed",
            triage=TriageResult(triage_id="tp_123", category="integration", confidence=0.87),
        )
        _, description, _ = normalize_payload(p)
        self.assertIn("LogPulse triage:", description)
        self.assertIn("category=integration", description)
        self.assertIn("confidence=0.87", description)
        self.assertIn("triage_id=tp_123", description)

    def test_other_source_no_prefix(self):
        p = IngestPayload(source="other", title="Manual incident")
        title, _, _ = normalize_payload(p)
        self.assertEqual(title, "Manual incident")

    def test_empty_description_falls_back_to_title(self):
        p = IngestPayload(source="other", title="Bare title", description="")
        _, description, _ = normalize_payload(p)
        self.assertEqual(description, "Bare title")


class TestDedupWindow(unittest.TestCase):
    def _row(self, age_hours: float):
        row = mock.Mock()
        row.last_reported_at = datetime.now(timezone.utc) - timedelta(hours=age_hours)
        return row

    def test_no_key_no_dedup(self):
        self.assertIsNone(check_dedup(DB, None))

    def test_recent_key_deduplicated(self):
        row = self._row(age_hours=1)
        db = mock.Mock()
        db.get.return_value = row
        self.assertIs(check_dedup(db, "alert:X:Y"), row)

    def test_expired_key_creates_new_ticket(self):
        row = self._row(age_hours=25)
        db = mock.Mock()
        db.get.return_value = row
        self.assertIsNone(check_dedup(db, "alert:X:Y"))

    def test_unknown_key_creates_new_ticket(self):
        db = mock.Mock()
        db.get.return_value = None
        self.assertIsNone(check_dedup(db, "order:42"))


if __name__ == "__main__":
    unittest.main()
