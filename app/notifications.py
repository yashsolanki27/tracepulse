"""Notifications: Slack webhook messaging for engineer assignment + SLA events."""
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


def _post_slack(text: str) -> bool:
    """POST a message to the configured Slack webhook.

    Fail-safe by design: any failure (unset URL, network error, timeout, bad
    response) is logged and swallowed so a caller can never fail because of
    notification problems. Returns True only if Slack returned 2xx.
    """
    if not SLACK_WEBHOOK_URL:
        logger.warning("Slack notification skipped: SLACK_WEBHOOK_URL not configured")
        return False

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
            logger.info("Slack notification sent (HTTP %d)", resp.status)
            return True
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.error("Slack notification failed: %s", exc)
        return False
    except Exception:
        logger.exception("Unexpected error sending Slack notification")
        return False


def notify_assignment(ticket_id: int, title: str, priority: str | None, engineer_name: str) -> bool:
    """POST an assignment message to the configured Slack webhook. Fail-safe."""
    text = (
        f":bell: Ticket #{ticket_id} assigned to {engineer_name}\n"
        f"*{title}*\nPriority: {priority or 'untriaged'}"
    )
    return _post_slack(text)


def notify_sla(ticket_id: int, title: str, sla_status: str, engineer_name: str | None = None) -> bool:
    """Notify on SLA warning/breach. Fail-safe like notify_assignment."""
    who = f" (assigned: {engineer_name})" if engineer_name else ""
    emoji = ":rotating_light:" if sla_status == "breached" else ":warning:"
    return _post_slack(
        f"{emoji} SLA {sla_status.upper()} — ticket #{ticket_id}{who}\n*{title}*"
    )