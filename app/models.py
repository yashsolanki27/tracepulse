from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


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
    resolution_text = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    embedding = Column(Vector(384), nullable=True)
