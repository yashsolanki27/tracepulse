"""External incident ingestion (PulseGrid integration).

Chain contract: PulseGrid producers call LogPulse /triage FIRST (unchanged),
then forward the triage result to this endpoint synchronously. This endpoint
deduplicates on the producer-supplied dedup_key and runs the created ticket
through the standard pipeline (RCA -> triage -> embedding -> similarity data
-> SLA deadline).

POST /ingest/webhook
Auth: X-API-Key (same key as the rest of the API).

Payload:
{
  "source": "alertmanager|reconciliation|newman|email|other",
  "title": "short incident title",
  "description": "longer description (optional)",
  "logs": "raw log/error text (optional)",
  "labels": {"alertname": "...", "instance": "...", ...},   # optional metadata
  "dedup_key": "alert:HighErrorRate:crm-service:8000",      # optional; enables dedup
  "triage": {"triage_id": "...", "category": "...", "confidence": 0.87}  # optional LogPulse result
}

Responses: 201 ticket created, 202 deduplicated (no new ticket), 422 bad payload.
"""
import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import verify_api_key
from database import get_db
from embeddings import embed_ticket
from models import IngestDedup, Ticket
from rca import analyze_ticket
from sla import compute_deadline

logger = logging.getLogger("tracepulse.ingest")

router = APIRouter(prefix="/ingest", tags=["ingest"])

_SOURCES = {"alertmanager", "reconciliation", "newman", "email", "other"}


class TriageResult(BaseModel):
    # LogPulse sends a numeric triage id; accept int or str and normalize.
    triage_id: int | str | None = None
    category: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class IngestPayload(BaseModel):
    source: str = "other"
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    logs: str = ""
    labels: dict[str, str] = {}
    dedup_key: str | None = Field(default=None, max_length=300)
    triage: TriageResult | None = None


class IngestResponse(BaseModel):
    status: str            # "created" | "deduplicated"
    ticket_id: int | None = None


def normalize_payload(payload: IngestPayload) -> tuple[str, str, str]:
    """Build (title, description, logs) for the ticket from the ingest envelope.

    Pure function (unit-testable): folds source/labels/triage context into the
    text so RCA and embeddings see a complete incident picture.
    """
    title = f"[{payload.source}] {payload.title.strip()}" if payload.source != "other" else payload.title.strip()

    desc_parts = [p for p in (payload.description.strip(),) if p]
    if payload.labels:
        labels_str = ", ".join(f"{k}={v}" for k, v in sorted(payload.labels.items()))
        desc_parts.append(f"Labels: {labels_str}")
    if payload.triage is not None:
        triage_str = f"LogPulse triage: category={payload.triage.category or 'n/a'}, confidence={payload.triage.confidence}"
        if payload.triage.triage_id:
            triage_str += f", triage_id={payload.triage.triage_id}"
        desc_parts.append(triage_str)
    description = "\n".join(desc_parts) or payload.title.strip()

    logs = payload.logs.strip()
    return title, description, logs


def check_dedup(db: Session, dedup_key: str | None) -> IngestDedup | None:
    """Return the prior dedup row if dedup_key is still inside the cooldown."""
    if not dedup_key:
        return None
    row = db.get(IngestDedup, dedup_key)
    if row is None:
        return None
    cooldown = timedelta(hours=int(os.getenv("INGEST_DEDUP_HOURS", "24")))
    if datetime.now(timezone.utc) - row.last_reported_at < cooldown:
        return row
    return None


@router.post("/webhook", response_model=IngestResponse)
def ingest_webhook(payload: IngestPayload, db: Session = Depends(get_db), _key: None = Depends(verify_api_key)):
    if payload.source not in _SOURCES:
        raise HTTPException(status_code=422, detail=f"Unknown source '{payload.source}'. Allowed: {sorted(_SOURCES)}")

    prior = check_dedup(db, payload.dedup_key)
    if prior is not None:
        logger.info("Ingest dedup hit for key=%s (ticket_id=%s)", payload.dedup_key, prior.ticket_id)
        return JSONResponse(status_code=202, content=IngestResponse(status="deduplicated", ticket_id=prior.ticket_id).model_dump())

    title, description, logs = normalize_payload(payload)
    ticket = Ticket(title=title, description=description, logs=logs)
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    # Standard pipeline: RCA (Groq) -> triage -> embedding -> SLA deadline.
    rca = analyze_ticket(title, description, logs)
    if rca:
        ticket.root_cause = rca["root_cause"]
        ticket.evidence = rca["evidence"]
        ticket.issue_area = rca["issue_area"]
        ticket.suggested_resolution = rca["suggested_resolution"]
        ticket.priority = rca.get("priority")
        ticket.ai_severity = rca.get("severity")
        ticket.issue_type = rca.get("issue_type")
        ticket.team = rca.get("team")
    ticket.embedding = embed_ticket(title, description)
    ticket.target_resolution_time = compute_deadline(ticket.created_at, ticket.priority)
    db.commit()
    db.refresh(ticket)

    if payload.dedup_key:
        db.merge(
            IngestDedup(
                dedup_key=payload.dedup_key,
                last_reported_at=datetime.now(timezone.utc),
                ticket_id=ticket.id,
                source=payload.source,
            )
        )
        db.commit()

    logger.info(
        "Ingested %s incident -> ticket #%d (dedup_key=%s, triage=%s)",
        payload.source, ticket.id, payload.dedup_key,
        payload.triage.category if payload.triage else None,
    )
    return IngestResponse(status="created", ticket_id=ticket.id)
