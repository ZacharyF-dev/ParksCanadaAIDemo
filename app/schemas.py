from datetime import datetime

from pydantic import BaseModel, Field

from app.models import TicketPriority, TicketStatus


class CommentCreate(BaseModel):
    author: str = Field(default="system")
    body: str


class CommentRead(BaseModel):
    id: int
    ticket_id: int
    author: str
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TicketEventRead(BaseModel):
    id: int
    ticket_id: int
    event_type: str
    actor: str
    field_name: str | None
    old_value: str | None
    new_value: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TicketCreate(BaseModel):
    title: str
    description: str = ""
    priority: TicketPriority = TicketPriority.MEDIUM
    assignee: str | None = None
    reporter: str = "system"


class TicketUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: TicketPriority | None = None
    assignee: str | None = None
    reporter: str | None = None
    status: TicketStatus | None = None
    actor: str = "system"


class TicketTransitionRequest(BaseModel):
    status: TicketStatus
    actor: str = "system"


class TicketRead(BaseModel):
    id: int
    key: str
    title: str
    description: str
    status: str
    priority: str
    assignee: str | None
    reporter: str
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class TicketDetail(TicketRead):
    comments: list[CommentRead]
    events: list[TicketEventRead]