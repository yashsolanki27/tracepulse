from datetime import datetime

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

    model_config = {"from_attributes": True}


class TicketResolve(BaseModel):
    resolution_text: str = Field(..., min_length=1)

    @field_validator("resolution_text", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        if isinstance(v, str) and not v.strip():
            raise ValueError("must not be empty or whitespace-only")
        return v.strip() if isinstance(v, str) else v
