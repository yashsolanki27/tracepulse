from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, true
from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Engineer(Base):
    __tablename__ = "engineers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    slack_handle = Column(String, nullable=True)
    active = Column(Boolean, nullable=False, default=True, server_default=true())


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    logs = Column(Text, nullable=False)
    system = Column(String, nullable=True)
    severity = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    root_cause = Column(Text, nullable=True)
    evidence = Column(Text, nullable=True)
    issue_area = Column(String, nullable=True)
    suggested_resolution = Column(Text, nullable=True)
    priority = Column(String, nullable=True)          # AI triage: low/medium/high/critical
    ai_severity = Column(String, nullable=True)       # AI triage; separate from manual `severity`
    issue_type = Column(String, nullable=True)        # AI triage: e.g. bug, outage, config, performance
    team = Column(String, nullable=True)              # AI triage: suggested owning team
    status = Column(
        String,
        nullable=False,
        default="open",
        server_default="open",
    )
    target_resolution_time = Column(DateTime(timezone=True), nullable=True)
    sla_status = Column(String, nullable=True)  # null / warning / breached
    assigned_engineer_id = Column(Integer, ForeignKey("engineers.id"), nullable=True)
    resolution_text = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    embedding = Column(Vector(384), nullable=True)


class IngestDedup(Base):
    """Dedup state for externally ingested incidents (PulseGrid chain).

    Keyed by an opaque dedup_key supplied by the producer (e.g. PulseGrid's
    "alert:{alertname}:{instance}" or "order:{id}"). A key seen within the
    cooldown window is acknowledged (202) without creating a new ticket.
    """

    __tablename__ = "ingest_dedup"

    dedup_key = Column(String, primary_key=True)
    last_reported_at = Column(DateTime(timezone=True), nullable=False)
    ticket_id = Column(Integer, nullable=True)
    source = Column(String, nullable=True)

