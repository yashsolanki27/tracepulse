"""Notifications: Slack webhook messaging for engineer assignment."""
import json
import logging
import os
import urllib.error
import urllib.request


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Slack webhooks answer 2xx directly; a redirect means the URL is bogus."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)

logger = logging.getLogger("tracepulse.notifications")

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SLACK_TIMEOUT_SECONDS = 5


def notify_assignment(ticket_id: int, title: str, priority: str | None, engineer_name: str) -> bool:
    """POST an assignment message to the configured Slack webhook.

    Fail-safe by design: any failure (unset URL, network error, timeout, bad
    response) is logged and swallowed so an assignment can never fail because
    of notification problems. Returns True only if Slack returned 2xx.
    """
    if not SLACK_WEBHOOK_URL:
        logger.warning(
            "Slack notification skipped for ticket_id=%d: SLACK_WEBHOOK_URL not configured", ticket_id
        )
        return False

    text = (
        f":bell: Ticket #{ticket_id} assigned to {engineer_name}\n"
        f"*{title}*\nPriority: {priority or 'untriaged'}"
    )
    body = json.dumps({"text": text}).encode()

    try:
        req = urllib.request.Request(
            SLACK_WEBHOOK_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        opener = urllib.request.build_opener(_NoRedirect)
        with opener.open(req, timeout=SLACK_TIMEOUT_SECONDS) as resp:
            logger.info(
                "Slack notification sent for ticket_id=%d to %s (HTTP %d)",
                ticket_id, engineer_name, resp.status,
            )
            return True
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.error(
            "Slack notification failed for ticket_id=%d (assigned to %s): %s",
            ticket_id, engineer_name, exc,
        )
        return False
    except Exception:
        logger.exception(
            "Unexpected error sending Slack notification for ticket_id=%d", ticket_id
        )
        return False