from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import verify_api_key
from database import get_db
from models import Ticket
from schemas import (
    ALLOWED_TRANSITIONS,
    SimilarIncident,
    TicketCreate,
    TicketDetail,
    TicketResolve,
    TicketResponse,
    TicketStatusUpdate,
)

from embeddings import embed_ticket
from rca import analyze_ticket
from similarity import find_similar

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("", response_model=TicketResponse, status_code=201)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db), _key: None = Depends(verify_api_key)):
    ticket = Ticket(**payload.model_dump())
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    rca = analyze_ticket(payload.title, payload.description, payload.logs)
    if rca:
        ticket.root_cause = rca["root_cause"]
        ticket.evidence = rca["evidence"]
        ticket.issue_area = rca["issue_area"]
        ticket.suggested_resolution = rca["suggested_resolution"]
        ticket.priority = rca.get("priority")
        ticket.ai_severity = rca.get("severity")
        ticket.issue_type = rca.get("issue_type")
        ticket.team = rca.get("team")
        db.commit()
        db.refresh(ticket)

    ticket.embedding = embed_ticket(payload.title, payload.description)
    db.commit()
    db.refresh(ticket)
    return ticket


@router.get("/{ticket_id}", response_model=TicketDetail)
def get_ticket(ticket_id: int, db: Session = Depends(get_db), _key: None = Depends(verify_api_key)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    similar = find_similar(db, ticket)
    return TicketDetail(
        **TicketResponse.model_validate(ticket).model_dump(),
        embedding=list(ticket.embedding) if ticket.embedding is not None else None,
        similar_incidents=[
            SimilarIncident(
                ticket_id=t.id,
                title=t.title,
                root_cause=t.root_cause,
                resolution_text=t.resolution_text,
                similarity=round(score, 4),
            )
            for t, score in similar
        ],
    )


@router.get("", response_model=list[TicketResponse])
def list_tickets(db: Session = Depends(get_db), _key: None = Depends(verify_api_key)):
    return db.query(Ticket).all()


@router.patch("/{ticket_id}/resolve", response_model=TicketResponse)
def resolve_ticket(ticket_id: int, payload: TicketResolve, db: Session = Depends(get_db), _key: None = Depends(verify_api_key)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    ticket.resolution_text = payload.resolution_text
    ticket.resolved_at = datetime.now(timezone.utc)
    ticket.status = "resolved"
    db.commit()
    db.refresh(ticket)
    return ticket


@router.patch("/{ticket_id}/status", response_model=TicketResponse)
def update_ticket_status(
    ticket_id: int, payload: TicketStatusUpdate, db: Session = Depends(get_db), _key: None = Depends(verify_api_key)
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    allowed = ALLOWED_TRANSITIONS.get(ticket.status, set())
    if payload.status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Invalid status transition: '{ticket.status}' -> '{payload.status}'. Allowed: {sorted(allowed)}",
        )
    ticket.status = payload.status
    db.commit()
    db.refresh(ticket)
    return ticket
