from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


TicketStatus = Literal["todo", "in_progress", "blocked", "done"]


class TicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    priority: Literal["low", "medium", "high"] = "medium"
    assignee: str | None = None


class TicketUpdateStatus(BaseModel):
    status: TicketStatus


class TicketAssign(BaseModel):
    assignee: str | None = Field(default=None, max_length=200)


class CommentCreate(BaseModel):
    author: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)


class Ticket(BaseModel):
    id: int
    key: str
    title: str
    description: str
    status: TicketStatus
    priority: str
    assignee: str | None
    created_at: datetime
    updated_at: datetime


class Comment(BaseModel):
    id: int
    ticket_id: int
    author: str
    body: str
    created_at: datetime