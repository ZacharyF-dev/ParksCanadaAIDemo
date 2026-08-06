from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


TicketStatus = Literal["todo", "in_progress", "blocked", "done"]
TicketCategory = Literal["hardware", "software", "network", "access", "other"]


class TicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    priority: Literal["low", "medium", "high"] = "medium"
    category: TicketCategory = "other"
    labels: list[str] = Field(default_factory=list)
    assignee: str | None = None
    requester: str | None = None
    due_at: str | None = None


class TicketEdit(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    priority: Literal["low", "medium", "high"] = "medium"
    category: TicketCategory = "other"
    assignee: str | None = Field(default=None, max_length=200)
    requester: str | None = Field(default=None, max_length=200)
    due_at: str | None = None
    actor: str = Field(default="dashboard", max_length=100)


class TicketUpdateStatus(BaseModel):
    status: TicketStatus
    actor: str = Field(default="dashboard", max_length=100)


class TicketAssign(BaseModel):
    assignee: str | None = Field(default=None, max_length=200)
    actor: str = Field(default="dashboard", max_length=100)


class TicketUpdateCategory(BaseModel):
    category: TicketCategory
    actor: str = Field(default="dashboard", max_length=100)


class TicketEscalate(BaseModel):
    reason: str = Field(default="", max_length=500)
    actor: str = Field(default="dashboard", max_length=100)


class CommentCreate(BaseModel):
    author: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)


class LabelUpdate(BaseModel):
    labels: list[str] = Field(default_factory=list)
    actor: str = Field(default="dashboard", max_length=100)


class WatcherUpdate(BaseModel):
    watcher: str = Field(min_length=1, max_length=200)
    actor: str = Field(default="dashboard", max_length=100)


class AttachmentCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(default="application/octet-stream", max_length=200)
    content_base64: str = Field(min_length=1)
    uploaded_by: str = Field(min_length=1, max_length=200)


class SavedFilterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    status: str | None = None
    category: str | None = None
    query: str | None = None
    labels: list[str] = Field(default_factory=list)


class BulkStatusUpdate(BaseModel):
    ticket_ids: list[int] = Field(min_length=1)
    status: TicketStatus
    actor: str = Field(default="dashboard", max_length=100)


class BulkAssignUpdate(BaseModel):
    ticket_ids: list[int] = Field(min_length=1)
    assignee: str | None = Field(default=None, max_length=200)
    actor: str = Field(default="dashboard", max_length=100)


class Ticket(BaseModel):
    id: int
    key: str
    title: str
    description: str
    status: TicketStatus
    priority: str
    category: TicketCategory
    assignee: str | None
    requester: str | None
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime


class Comment(BaseModel):
    id: int
    ticket_id: int
    author: str
    body: str
    created_at: datetime


class ActivityEntry(BaseModel):
    id: int
    ticket_id: int
    actor: str
    event_type: str
    detail: str
    created_at: datetime