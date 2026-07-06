from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crud import add_comment, create_ticket, get_ticket, list_tickets, transition_ticket, update_ticket
from app.db import get_db
from app.schemas import CommentCreate, TicketCreate, TicketTransitionRequest, TicketUpdate

router = APIRouter(prefix="/mcp", tags=["mcp"])


def _authorize(x_api_token: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if settings.secret_internal_api_token and x_api_token != settings.secret_internal_api_token:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/tools")
def get_tools(_: None = Depends(_authorize)) -> dict[str, Any]:
    return {
        "tools": [
            {
                "name": "create_ticket",
                "description": "Create a new ticket",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "priority": {"type": "string", "enum": ["Low", "Medium", "High", "Critical"]},
                        "assignee": {"type": ["string", "null"]},
                        "reporter": {"type": "string"},
                    },
                    "required": ["title"],
                },
            },
            {
                "name": "get_ticket",
                "description": "Get ticket details by numeric ticket id",
                "input_schema": {
                    "type": "object",
                    "properties": {"ticket_id": {"type": "integer"}},
                    "required": ["ticket_id"],
                },
            },
            {
                "name": "list_tickets",
                "description": "List tickets with optional filters",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "priority": {"type": "string"},
                        "assignee": {"type": "string"},
                        "search": {"type": "string"},
                    },
                },
            },
            {
                "name": "update_ticket",
                "description": "Update mutable ticket fields",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "ticket_id": {"type": "integer"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "priority": {"type": "string"},
                        "assignee": {"type": ["string", "null"]},
                        "reporter": {"type": "string"},
                        "status": {"type": "string"},
                        "actor": {"type": "string"},
                    },
                    "required": ["ticket_id"],
                },
            },
            {
                "name": "transition_ticket",
                "description": "Transition a ticket through workflow statuses",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "ticket_id": {"type": "integer"},
                        "status": {"type": "string", "enum": ["Open", "In Progress", "Resolved", "Closed"]},
                        "actor": {"type": "string"},
                    },
                    "required": ["ticket_id", "status"],
                },
            },
            {
                "name": "add_comment",
                "description": "Add a comment to a ticket",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "ticket_id": {"type": "integer"},
                        "author": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["ticket_id", "body"],
                },
            },
            {
                "name": "get_ticket_history",
                "description": "Get comments and events for a ticket",
                "input_schema": {
                    "type": "object",
                    "properties": {"ticket_id": {"type": "integer"}},
                    "required": ["ticket_id"],
                },
            },
        ]
    }


@router.post("/call")
def call_tool(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    _: None = Depends(_authorize),
) -> dict[str, Any]:
    tool_name = payload.get("tool")
    arguments = payload.get("arguments", {})

    if not tool_name:
        raise HTTPException(status_code=400, detail="Missing tool")

    if tool_name == "create_ticket":
        ticket = create_ticket(db, TicketCreate(**arguments))
        return {"result": {"id": ticket.id, "key": ticket.key}}

    if tool_name == "get_ticket":
        ticket = get_ticket(db, int(arguments["ticket_id"]))
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return {
            "result": {
                "id": ticket.id,
                "key": ticket.key,
                "title": ticket.title,
                "description": ticket.description,
                "status": ticket.status,
                "priority": ticket.priority,
                "assignee": ticket.assignee,
                "reporter": ticket.reporter,
                "comments": [
                    {"id": c.id, "author": c.author, "body": c.body, "created_at": c.created_at.isoformat()}
                    for c in ticket.comments
                ],
                "events": [
                    {
                        "id": e.id,
                        "event_type": e.event_type,
                        "actor": e.actor,
                        "field_name": e.field_name,
                        "old_value": e.old_value,
                        "new_value": e.new_value,
                        "created_at": e.created_at.isoformat(),
                    }
                    for e in ticket.events
                ],
            }
        }

    if tool_name == "list_tickets":
        tickets = list_tickets(
            db,
            status=arguments.get("status"),
            priority=arguments.get("priority"),
            assignee=arguments.get("assignee"),
            search=arguments.get("search"),
        )
        return {
            "result": [
                {
                    "id": t.id,
                    "key": t.key,
                    "title": t.title,
                    "status": t.status,
                    "priority": t.priority,
                    "assignee": t.assignee,
                }
                for t in tickets
            ]
        }

    if tool_name == "update_ticket":
        ticket = get_ticket(db, int(arguments["ticket_id"]))
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        updated = update_ticket(db, ticket, TicketUpdate(**arguments))
        return {"result": {"id": updated.id, "key": updated.key, "status": updated.status}}

    if tool_name == "transition_ticket":
        ticket = get_ticket(db, int(arguments["ticket_id"]))
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        try:
            updated = transition_ticket(db, ticket, TicketTransitionRequest(**arguments))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"result": {"id": updated.id, "key": updated.key, "status": updated.status}}

    if tool_name == "add_comment":
        ticket = get_ticket(db, int(arguments["ticket_id"]))
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        comment = add_comment(db, ticket, CommentCreate(**arguments))
        return {"result": {"id": comment.id, "ticket_id": comment.ticket_id}}

    if tool_name == "get_ticket_history":
        ticket = get_ticket(db, int(arguments["ticket_id"]))
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return {
            "result": {
                "comments": [
                    {"id": c.id, "author": c.author, "body": c.body, "created_at": c.created_at.isoformat()}
                    for c in ticket.comments
                ],
                "events": [
                    {
                        "id": e.id,
                        "event_type": e.event_type,
                        "actor": e.actor,
                        "field_name": e.field_name,
                        "old_value": e.old_value,
                        "new_value": e.new_value,
                        "created_at": e.created_at.isoformat(),
                    }
                    for e in ticket.events
                ],
            }
        }

    raise HTTPException(status_code=404, detail=f"Unknown tool '{tool_name}'")