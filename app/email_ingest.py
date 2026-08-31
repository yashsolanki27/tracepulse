"""Phase 2e: email ingestion.

An IMAP poller reads unseen mail from a support inbox, extracts
title (subject) and description (plain-text body), and creates a ticket by
calling the existing POST /tickets endpoint over HTTP — the exact same
endpoint, validation and RCA/triage/similarity/SLA/assignment pipeline as
manual ticket creation. Nothing in the core pipeline is touched.

Configuration (alongside DATABASE_URL / GROQ_API_KEY / TRACEPULSE_API_KEY):
    EMAIL_IMAP_HOST      IMAP server hostname (e.g. imap.gmail.com).
                         When unset, the poller is disabled entirely.
    EMAIL_IMAP_PORT      IMAP port (default 993, TLS).
    EMAIL_USER           Inbox username.
    EMAIL_PASSWORD       Inbox password / app password.
    EMAIL_FOLDER         Mailbox folder to watch (default INBOX).
    EMAIL_POLL_SECONDS   Poll interval (default 60).
    TRACEPULSE_API_URL   Base URL of this API (default http://localhost:8000).
    TRACEPULSE_API_KEY   Already required by the API; reused to authenticate
                         the POST /tickets call.
"""
import email
import email.header
import imaplib
import json
import logging
import os
import re
import urllib.error
import urllib.request
from email.message import Message

logger = logging.getLogger("tracepulse.email")

MAX_DESCRIPTION_LEN = 10_000


def _decode_header(value: str | None) -> str:
    """Decode a RFC2047-encoded header (e.g. '=?utf-8?Q?...?=') to a str."""
    if not value:
        return ""
    parts = email.header.decode_header(value)
    decoded = []
    for data, charset in parts:
        if isinstance(data, bytes):
            decoded.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(data)
    return "".join(decoded).strip()


def _strip_html(html: str) -> str:
    """Crude HTML -> text: drop <style>/<script>, tags, collapse whitespace."""
    text = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _part_body(part: Message) -> str:
    payload = part.get_payload(decode=True) or b""
    charset = part.get_content_charset() or "utf-8"
    text = payload.decode(charset, errors="replace")
    if part.get_content_subtype() == "html":
        return _strip_html(text)
    return text.strip()


def extract_title_description(msg: Message) -> tuple[str, str]:
    """Extract (title, description) from an email message.

    title       = decoded Subject (falls back to '(no subject)').
    description = first text/plain part; if none, text/html with tags stripped.
    """
    title = _decode_header(msg.get("Subject")) or "(no subject)"

    description = ""
    if msg.is_multipart():
        plain = html = None
        for part in msg.walk():
            if part.is_multipart() or part.get_content_maintype() != "text":
                continue
            if "attachment" in (part.get("Content-Disposition") or ""):
                continue
            if part.get_content_subtype() == "plain" and plain is None:
                plain = _part_body(part)
            elif part.get_content_subtype() == "html" and html is None:
                html = _part_body(part)
        description = plain or html or ""
    elif msg.get_content_maintype() == "text":
        description = _part_body(msg)

    if len(description) > MAX_DESCRIPTION_LEN:
        description = description[:MAX_DESCRIPTION_LEN]
    return title, description

    """Decode a RFC2047-encoded header (e.g. '=?utf-8?Q?...?=') to a str."""
    if not value:
        return ""
    parts = email.header.decode_header(value)
    decoded = []
    for data, charset in parts:
        if isinstance(data, bytes):
            decoded.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(data)
    return "".join(decoded).strip()

def create_ticket_from_mail(title: str, description: str) -> int | None:
    """POST {title, description} to the existing POST /tickets endpoint.

    Returns the new ticket id, or None on failure (logged, never raised —
    one bad email must never break the poller).
    """
    base_url = os.getenv("TRACEPULSE_API_URL", "http://localhost:8000").rstrip("/")
    api_key = os.getenv("TRACEPULSE_API_KEY", "")
    body = json.dumps(
        {"title": title, "description": description, "logs": description}
    ).encode()
    req = urllib.request.Request(
        f"{base_url}/tickets",
        data=body,
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    try:
        # Ticket creation runs the full pipeline (Groq RCA + embedding) which
        # can take well over 30s — give it 3 minutes.
        with urllib.request.urlopen(req, timeout=180) as resp:
            ticket = json.loads(resp.read())
            ticket_id = ticket.get("id")
            logger.info("Email created ticket id=%s title=%r", ticket_id, title)
            return ticket_id
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
        logger.error("Failed to create ticket from email (title=%r): %s", title, exc)
        return None


def poll_inbox() -> None:
    """Scheduled job: fetch unseen mail and turn each into a ticket.

    Wrapped in try/except so a transient IMAP failure never kills the
    scheduler or the app (same pattern as the SLA job).
    """
    try:
        _poll_inbox_inner()
    except Exception:
        logger.exception("Email poll job failed; scheduler will retry on next interval")


def _poll_inbox_inner() -> None:
    host = os.getenv("EMAIL_IMAP_HOST")
    if not host:
        return
    user = os.getenv("EMAIL_USER", "")
    password = os.getenv("EMAIL_PASSWORD", "")
    folder = os.getenv("EMAIL_FOLDER", "INBOX")
    port = int(os.getenv("EMAIL_IMAP_PORT", "993"))

    conn = imaplib.IMAP4_SSL(host, port)
    try:
        conn.login(user, password)
        conn.select(folder)
        status, data = conn.search(None, "UNSEEN")
        if status != "OK":
            logger.warning("IMAP search failed: %s", status)
            return
        ids = data[0].split()
        if ids:
            logger.info("Email poll: %d unseen message(s)", len(ids))
        for mail_id in ids:
            status, msg_data = conn.fetch(mail_id, "(RFC822)")
            if status != "OK" or not msg_data or msg_data[0] is None:
                logger.warning("IMAP fetch failed for id=%s", mail_id)
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            title, description = extract_title_description(msg)
            if not description:
                logger.warning("Skipping email id=%s: empty body (title=%r)", mail_id, title)
                # Mark seen anyway so we never loop on it forever.
                conn.store(mail_id, "+FLAGS", "\\Seen")
                continue
            ticket_id = create_ticket_from_mail(title, description)
            if ticket_id is not None:
                conn.store(mail_id, "+FLAGS", "\\Seen")
    finally:
        try:
            conn.logout()
        except Exception:
            pass
