"""Pure unit tests — no network, no DB. External calls mocked."""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from fastapi import HTTPException  # noqa: E402


class TestAuth(unittest.TestCase):
    def test_missing_key_401(self):
        from auth import verify_api_key
        with mock.patch.dict(os.environ, {"TRACEPULSE_API_KEY": "secret"}):
            with self.assertRaises(HTTPException) as cm:
                verify_api_key(None)
            self.assertEqual(cm.exception.status_code, 401)

    def test_wrong_key_401(self):
        from auth import verify_api_key
        with mock.patch.dict(os.environ, {"TRACEPULSE_API_KEY": "secret"}):
            with self.assertRaises(HTTPException) as cm:
                verify_api_key("nope")
            self.assertEqual(cm.exception.status_code, 401)

    def test_correct_key_ok(self):
        from auth import verify_api_key
        with mock.patch.dict(os.environ, {"TRACEPULSE_API_KEY": "secret"}):
            self.assertIsNone(verify_api_key("secret"))

    def test_unconfigured_500(self):
        from auth import verify_api_key
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as cm:
                verify_api_key("anything")
            self.assertEqual(cm.exception.status_code, 500)


class TestSchemas(unittest.TestCase):
    def test_create_strips_whitespace(self):
        from schemas import TicketCreate
        t = TicketCreate(title="  DB down  ", description=" x ", logs=" y ")
        self.assertEqual(t.title, "DB down")

    def test_create_rejects_blank(self):
        from pydantic import ValidationError
        from schemas import TicketCreate
        with self.assertRaises(ValidationError):
            TicketCreate(title="   ", description="x", logs="y")

    def test_closed_is_terminal(self):
        from schemas import ALLOWED_TRANSITIONS
        self.assertNotIn("open", ALLOWED_TRANSITIONS["closed"])
        self.assertIn("in_progress", ALLOWED_TRANSITIONS["resolved"])
def _fake_completion(payload: dict):
    """Mock OpenAI chat response whose message content is `payload` as JSON."""
    msg = mock.Mock()
    msg.content = json.dumps(payload)
    resp = mock.Mock()
    resp.choices = [mock.Mock(message=msg)]
    return resp


VALID_RCA = {
    "root_cause": "deadlock", "evidence": "lock log", "issue_area": "db",
    "suggested_resolution": "add index", "priority": "HIGH",
    "severity": "major", "issue_type": "bug", "team": "platform",
}


class TestRca(unittest.TestCase):
    def test_valid_rca_and_triage(self):
        import rca
        with mock.patch.object(rca, "_client") as c:
            c.return_value.chat.completions.create.return_value = _fake_completion(VALID_RCA)
            out = rca.analyze_ticket("t", "d", "l")
        self.assertEqual(out["root_cause"], "deadlock")
        self.assertEqual(out["priority"], "high")  # normalized lowercase
        self.assertEqual(out["severity"], "major")

    def test_invalid_triage_value_dropped(self):
        import rca
        data = dict(VALID_RCA, priority="apocalypse")
        with mock.patch.object(rca, "_client") as c:
            c.return_value.chat.completions.create.return_value = _fake_completion(data)
            out = rca.analyze_ticket("t", "d", "l")
        self.assertIsNone(out["priority"])

    def test_none_on_garbage_after_retry(self):
        import rca
        bad = mock.Mock()
        bad.content = "not json"
        with mock.patch.object(rca, "_client") as c:
            c.return_value.chat.completions.create.return_value = mock.Mock(
                choices=[mock.Mock(message=bad)])
            self.assertIsNone(rca.analyze_ticket("t", "d", "l"))
            self.assertEqual(c.return_value.chat.completions.create.call_count, 2)


class TestSla(unittest.TestCase):
    def test_deadline_by_priority(self):
        from sla import SLA_HOURS, compute_deadline
        created = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for prio, hours in SLA_HOURS.items():
            self.assertEqual(compute_deadline(created, prio), created + timedelta(hours=hours))

    def test_deadline_null_priority_default(self):
        from sla import DEFAULT_SLA_HOURS, compute_deadline
        created = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(
            compute_deadline(created, None), created + timedelta(hours=DEFAULT_SLA_HOURS))

    def _ticket(self, sla_status=None, status="open", created=None, target=None):
        t = mock.Mock()
        t.sla_status = sla_status
        t.status = status
        now = datetime.now(timezone.utc)
        t.created_at = created or (now - timedelta(minutes=1))
        t.target_resolution_time = target or (now + timedelta(hours=10))
        return t

    def _run(self, tickets):
        import sla
        # Adaptation vs brief: _check_slas_inner imports SessionLocal from
        # `database` and or_ from `sqlalchemy` *inside the function*, so we
        # patch at those source modules, not on `sla`. The real query chain is
        # .query().filter().filter().filter().all() — three filters, not two.
        with mock.patch("database.SessionLocal") as s, \
                mock.patch("sqlalchemy.or_", lambda *a: True):
            s.return_value.query.return_value.filter.return_value \
                .filter.return_value.filter.return_value.all.return_value = tickets
            sla.check_slas()

    def test_breach(self):
        t = self._ticket(target=datetime.now(timezone.utc) - timedelta(minutes=1))
        self._run([t])
        self.assertEqual(t.sla_status, "breached")

    def test_warning_at_80pct(self):
        now = datetime.now(timezone.utc)
        t = self._ticket(created=now - timedelta(hours=8), target=now + timedelta(hours=2))
        self._run([t])
        self.assertEqual(t.sla_status, "warning")

    def test_never_downgrade(self):
        now = datetime.now(timezone.utc)
        t = self._ticket(sla_status="breached", created=now - timedelta(minutes=5),
                         target=now + timedelta(hours=10))
        self._run([t])
        self.assertEqual(t.sla_status, "breached")

    def test_resolved_tickets_skipped(self):
        t = self._ticket(status="resolved")
        self._run([t])
        self.assertIsNone(t.sla_status)


class TestNotifications(unittest.TestCase):
    def test_skips_without_url(self):
        import notifications
        with mock.patch.object(notifications, "SLACK_WEBHOOK_URL", ""):
            self.assertFalse(notifications.notify_assignment(1, "t", "high", "Eng"))

    def test_returns_true_on_2xx(self):
        import notifications
        fake_resp = mock.MagicMock()
        fake_resp.__enter__.return_value.status = 200
        with mock.patch.object(notifications, "SLACK_WEBHOOK_URL", "http://hook"), \
             mock.patch("urllib.request.build_opener") as op:
            op.return_value.open.return_value = fake_resp
            self.assertTrue(notifications.notify_assignment(1, "t", "high", "Eng"))

    def test_fail_safe_on_network_error(self):
        import urllib.error
        import notifications
        with mock.patch.object(notifications, "SLACK_WEBHOOK_URL", "http://hook"), \
             mock.patch("urllib.request.build_opener") as op:
            op.return_value.open.side_effect = urllib.error.URLError("down")
            self.assertFalse(notifications.notify_assignment(1, "t", "high", "Eng"))


class TestSlaNotify(unittest.TestCase):
    def test_notify_sla_called_on_transition(self):
        import sla
        now = datetime.now(timezone.utc)
        t = mock.Mock()
        t.id = 7
        t.title = "DB down"
        t.sla_status = None
        t.status = "open"
        t.created_at = now - timedelta(hours=9)
        t.target_resolution_time = now + timedelta(hours=1)
        t.assigned_engineer_id = 1
        eng = mock.Mock()
        eng.name = "Dana"
        # Adaptation vs brief: _check_slas_inner imports SessionLocal from
        # `database` and or_ from `sqlalchemy` *inside the function*, so we
        # patch at those source modules, not on `sla`. The real query chain is
        # .query().filter().filter().filter().all() — three filters, not two.
        # The engineer lookup reuses the shared .filter child mock's .first.
        with mock.patch("database.SessionLocal") as s, \
                mock.patch("sqlalchemy.or_", lambda *a: True), \
                mock.patch("sla.notify_sla") as ns:
            s.return_value.query.return_value.filter.return_value \
                .filter.return_value.filter.return_value.all.return_value = [t]
            s.return_value.query.return_value.filter.return_value.first.return_value = eng
            sla.check_slas()
        ns.assert_called_once_with(7, "DB down", "warning", "Dana")


if __name__ == "__main__":
    unittest.main()

