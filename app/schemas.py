from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TicketCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    logs: str = Field(..., min_length=1)
    system: str | None = None
    severity: str | None = None

    @field_validator("title", "description", "logs", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        if isinstance(v, str) and not v.strip():
            raise ValueError("must not be empty or whitespace-only")
        return v.strip() if isinstance(v, str) else v


class TicketResponse(BaseModel):
    id: int
    title: str
    description: str
    logs: str
    system: str | None
    severity: str | None
    created_at: datetime
    root_cause: str | None
    evidence: str | None
    issue_area: str | None
    suggested_resolution: str | None
    resolution_text: str | None
    resolved_at: datetime | None
    status: str
    priority: str | None
    ai_severity: str | None
    issue_type: str | None
    team: str | None
    target_resolution_time: datetime | None
    sla_status: str | None

    model_config = {"from_attributes": True}


class SimilarIncident(BaseModel):
    ticket_id: int
    title: str
    root_cause: str | None
    resolution_text: str | None
    similarity: float


class TicketDetail(TicketResponse):
    embedding: list[float] | None
    similar_incidents: list[SimilarIncident] = []


class TicketResolve(BaseModel):
    resolution_text: str = Field(..., min_length=1)

    @field_validator("resolution_text", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        if isinstance(v, str) and not v.strip():
            raise ValueError("must not be empty or whitespace-only")
        return v.strip() if isinstance(v, str) else v


VALID_STATUSES = ("open", "in_progress", "resolved", "closed")

# Simple state machine: closed is terminal; resolved may only close or go back
# to in_progress; open/in_progress may move freely among open/in_progress/resolved/closed.
ALLOWED_TRANSITIONS = {
    "open": {"open", "in_progress", "resolved", "closed"},
    "in_progress": {"open", "in_progress", "resolved", "closed"},
    "resolved": {"closed", "in_progress"},
    "closed": set(),
}


class TicketStatusUpdate(BaseModel):
    status: Literal["open", "in_progress", "resolved", "closed"]
