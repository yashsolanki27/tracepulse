from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import verify_api_key
from database import get_db
from models import Ticket
from schemas import TicketCreate, TicketResolve, TicketResponse

from rca import analyze_ticket

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
        db.commit()
        db.refresh(ticket)
    return ticket


@router.get("/{ticket_id}", response_model=TicketResponse)
def get_ticket(ticket_id: int, db: Session = Depends(get_db), _key: None = Depends(verify_api_key)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


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
    db.commit()
    db.refresh(ticket)
    return ticket
