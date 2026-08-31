# TracePulse ⇄ PulseGrid Integration (Chain Mode)

TracePulse ingests incidents created by [PulseGrid](https://github.com/yashsolanki27/pulsegrid).
**Chain order is fixed**: PulseGrid → LogPulse `/triage` first (unchanged), then the
triage result is forwarded to TracePulse synchronously. LogPulse classifies,
TracePulse manages the incident (RCA, similarity, SLA, engineer assignment).

```
Alertmanager / reconciliation-job / Newman
        │  1. POST {"log_text": ...}          (existing, unchanged)
        ▼
    LogPulse /triage  ──► id, category, confidence
        │  2. only on success: POST /ingest/webhook with triage result
        ▼
    TracePulse  ──► ticket created (RCA + embedding + SLA) or 202 deduplicated
```

## TracePulse side (implemented here)

**`POST /ingest/webhook`** — auth: `X-API-Key` (same key as the rest of the API).

```json
{
  "source": "alertmanager | reconciliation | newman | email | other",
  "title": "short incident title",
  "description": "optional longer description",
  "logs": "optional raw error/log text",
  "labels": {"alertname": "...", "instance": "...", "order_id": "77"},
  "dedup_key": "order:77",
  "triage": {"triage_id": "tp_991", "category": "integration", "confidence": 0.92}
}
```

Responses:
- `201 {"status":"created","ticket_id":40}` — new incident, full pipeline ran
  (Groq RCA → triage → embedding → SLA deadline).
- `202 {"status":"deduplicated","ticket_id":40}` — `dedup_key` already seen
  within the cooldown window (default 24h, tune with `INGEST_DEDUP_HOURS` in
  `.env`). State is persisted in the `ingest_dedup` table.
- `401` missing/invalid API key, `422` unknown `source` or bad payload.

The ticket title is prefixed with `[source]`, and labels + the LogPulse triage
result are folded into the description so RCA and similarity see full context.

## PulseGrid side (changes to apply in that repo)

**1. `pulsegrid_common/` — add a TracePulse client** (mirror of
`logpulse_client.py`):

```python
# pulsegrid_common/tracepulse_client.py
import os
import httpx
from dataclasses import dataclass


@dataclass
class IngestResult:
    ticket_id: int | None
    status: str


def post_to_tracepulse(
    *,
    url: str | None = None,
    api_key: str,
    source: str,
    title: str,
    description: str = "",
    logs: str = "",
    labels: dict[str, str] | None = None,
    dedup_key: str | None = None,
    triage: dict | None = None,
    timeout: float = 240.0,
) -> IngestResult | None:
    """Forward a triaged incident to TracePulse. Returns None on failure
    (caller must NOT update dedup state, mirroring the LogPulse contract)."""
    url = url or os.environ.get(
        "TRACEPULSE_URL", "http://localhost:8001/ingest/webhook"
    )
    payload = {
        "source": source,
        "title": title[:300],
        "description": description[:20000],
        "logs": logs[:20000],
        "labels": labels or {},
        "dedup_key": dedup_key,
        "triage": triage,
    }
    try:
        resp = httpx.post(
            url,
            json=payload,
            headers={"X-API-Key": api_key},
            timeout=timeout,
        )
        if resp.status_code in (201, 202):
            body = resp.json()
            return IngestResult(
                ticket_id=body.get("ticket_id"), status=body.get("status", "")
            )
        return None
    except Exception:
        return None
```

**2. `webhook-receiver/app/main.py`** — inside the `if result is not None:`
branch after `post_to_logpulse(...)` succeeds (before `mark_reported`):

```python
        # Chain step 2: forward the triaged alert to TracePulse.
        tp = post_to_tracepulse(
            api_key=os.environ["TRACEPULSE_API_KEY"],
            source="alertmanager",
            title=f"{alertname} on {instance}",
            description=f"{summary}. {description}",
            logs=log_text,
            labels=dict(labels),
            dedup_key=dedup_key,
            triage={
                "triage_id": result.id,
                "category": result.category,
                "confidence": result.confidence,
            },
        )
        if tp is None:
            log.warning("TracePulse failed for alert %s -- dedup NOT updated.", dedup_key)
            continue  # next run retries both calls
```

**3. `reconciliation-job/run.py`** — same pattern in the `if result is not
None:` branch:

```python
            tp = post_to_tracepulse(
                api_key=os.environ["TRACEPULSE_API_KEY"],
                source="reconciliation",
                title=f"CRM order {order_id} has no ERP invoice",
                description=log_text,
                labels={"order_id": str(order_id)},
                dedup_key=dedup_key,
                triage={
                    "triage_id": result.id,
                    "category": result.category,
                    "confidence": result.confidence,
                },
            )
            if tp is None:
                log.warning("order_id=%d: TracePulse failed -- dedup NOT updated.", order_id)
                continue
```

**4. Environment** (`.env` on both sides):

```bash
# PulseGrid .env
TRACEPULSE_URL=http://<tracepulse-host>/ingest/webhook   # VM behind Caddy: http://<VM_IP>/api/ingest/webhook
TRACEPULSE_API_KEY=<same value as TracePulse's TRACEPULSE_API_KEY>

# TracePulse .env (optional tuning)
INGEST_DEDUP_HOURS=24
```

Failure semantics match the existing LogPulse contract exactly: a TracePulse
failure means dedup state is **not** updated, so the next run retries the
whole chain. Note the chain re-calls LogPulse on retry — that is acceptable
(LogPulse dedup is advisory); TracePulse's `dedup_key` already prevents
duplicate tickets either way.

## Verification (done locally, 2026-08-31)

- `uv run --with pytest pytest tests` — 18 passed (9 new ingest tests)
- Live chain simulation: ingest payload with `dedup_key=order:77` → ticket #40
  created with RCA (root_cause set), priority=high, 5 similar incidents, SLA
  deadline +8h; second call → `202 deduplicated` (same ticket); no key → 401.
