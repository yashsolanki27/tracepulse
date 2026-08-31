"""Unit tests for Phase 2e email ingestion (title/description extraction).

Run from repo root:  .venv\\Scripts\\python -m unittest tests.test_email_ingest -v
These tests are pure (no network, no DB): they verify mail parsing and that
create_ticket_from_mail issues a correct POST to /tickets.
"""
import json
import sys
import unittest
import urllib.request
from email.message import EmailMessage
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import email_ingest  # noqa: E402


def make_simple_mail(subject: str, body: str) -> bytes:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "user@example.com"
    msg["To"] = "support@tracepulse.dev"
    msg.set_content(body)
    return msg.as_bytes()


class TestExtractTitleDescription(unittest.TestCase):
    def test_simple_plain_text_mail(self):
        raw = make_simple_mail("Payment gateway down", "Checkout returns 502s since 10:00 UTC.")
        msg = email_ingest.email.message_from_bytes(raw)
        title, description = email_ingest.extract_title_description(msg)
        self.assertEqual(title, "Payment gateway down")
        self.assertIn("Checkout returns 502s", description)

    def test_multipart_prefers_plain_text(self):
        raw = make_simple_mail(
            "DB latency",
            "Queries on orders table take 8s.",
        )
        msg = email_ingest.email.message_from_bytes(raw)
        title, description = email_ingest.extract_title_description(msg)
        self.assertEqual(title, "DB latency")
        self.assertEqual(description, "Queries on orders table take 8s.")

    def test_html_only_mail_is_stripped(self):
        msg = EmailMessage()
        msg["Subject"] = "Disk alert"
        msg.set_content("<p>/var/log at <b>98%</b></p><style>p{}</style>", subtype="html")
        title, description = email_ingest.extract_title_description(msg)
        self.assertEqual(title, "Disk alert")
        self.assertIn("98%", description)
        self.assertNotIn("<", description)
        self.assertNotIn("p{}", description)

    def test_encoded_subject(self):
        raw = make_simple_mail(" café outage ", "body")
        msg = email_ingest.email.message_from_bytes(raw)
        title, _ = email_ingest.extract_title_description(msg)
        self.assertEqual(title, "café outage")

    def test_missing_subject_fallback(self):
        raw = make_simple_mail("x", "body")
        msg = email_ingest.email.message_from_bytes(raw)
        msg.replace_header("Subject", "")
        title, description = email_ingest.extract_title_description(msg)
        self.assertEqual(title, "(no subject)")
        self.assertEqual(description, "body")

    def test_attachment_ignored(self):
        msg = EmailMessage()
        msg["Subject"] = "With attachment"
        msg.set_content("Main body here")
        msg.add_attachment(b"BIN" * 10, maintype="application", subtype="octet-stream", filename="a.bin")
        _, description = email_ingest.extract_title_description(msg)
        self.assertEqual(description, "Main body here")


class TestCreateTicketFromMail(unittest.TestCase):
    def test_posts_to_tickets_endpoint_with_api_key(self):
        captured = {}

        def fake_urlopen(req, timeout):
            captured["url"] = req.full_url
            captured["headers"] = dict(req.header_items())
            captured["body"] = json.loads(req.data)
            resp = mock.MagicMock()
            resp.__enter__.return_value.read.return_value = json.dumps(
                {"id": 42, "title": captured["body"]["title"]}
            ).encode()
            resp.read.return_value = resp.__enter__.return_value.read.return_value
            return resp

        with mock.patch.dict("os.environ", {"TRACEPULSE_API_URL": "http://api:8000/", "TRACEPULSE_API_KEY": "k-123"}):
            with mock.patch.object(urllib.request, "urlopen", side_effect=fake_urlopen):
                ticket_id = email_ingest.create_ticket_from_mail("API down", "5xx on /v1/orders")

        self.assertEqual(ticket_id, 42)
        self.assertEqual(captured["url"], "http://api:8000/tickets")
        self.assertEqual(
            captured["body"],
            {"title": "API down", "description": "5xx on /v1/orders", "logs": "5xx on /v1/orders"},
        )
        headers = {k.lower(): v for k, v in captured["headers"].items()}
        self.assertEqual(headers.get("x-api-key"), "k-123")

    def test_returns_none_on_connection_error(self):
        with mock.patch.dict("os.environ", {"TRACEPULSE_API_URL": "http://127.0.0.1:1"}):
            ticket_id = email_ingest.create_ticket_from_mail("t", "unreachable")
        self.assertIsNone(ticket_id)


if __name__ == "__main__":
    unittest.main()
