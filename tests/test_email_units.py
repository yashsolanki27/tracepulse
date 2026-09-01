"""Unit tests for email_ingest helpers (no IMAP, no network)."""
import email as email_lib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))


class TestLoopGuard(unittest.TestCase):
    def test_subject_with_tracepulse_tag_skipped(self):
        from email_ingest import should_skip_subject
        self.assertTrue(should_skip_subject("[TracePulse] Ticket #3 assigned"))
        self.assertFalse(should_skip_subject("DB down in prod"))


class TestHtmlExtraction(unittest.TestCase):
    def test_html_body_converted_to_text(self):
        from email_ingest import body_text_from_message
        raw = (
            b"From: a@b.c\r\nSubject: Help\r\nMIME-Version: 1.0\r\n"
            b"Content-Type: text/html; charset=utf-8\r\n\r\n"
            b"<html><body><p>Disk is <b>full</b> on /var</p></body></html>"
        )
        msg = email_lib.message_from_bytes(raw)
        self.assertIn("Disk is full on /var", body_text_from_message(msg))

    def test_plain_body_passthrough(self):
        from email_ingest import body_text_from_message
        raw = (
            b"From: a@b.c\r\nSubject: Help\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n\r\njust text"
        )
        msg = email_lib.message_from_bytes(raw)
        self.assertEqual(body_text_from_message(msg), "just text")


if __name__ == "__main__":
    unittest.main()
