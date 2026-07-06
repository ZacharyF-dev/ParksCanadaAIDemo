from __future__ import annotations

import logging

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import Comment, Ticket, TicketEvent, TicketPriority, TicketStatus
from app.schemas import CommentCreate, TicketCreate, TicketTransitionRequest, TicketUpdate

logger = logging.getLogger(__name__)


def _next_ticket_key(db: Session) -> str:
    """
    Generate the next ticket key using the configured project prefix.
    This is simple and sufficient for internal testing.
    """
    settings = get_settings()
    count = db.scalar(select(func.count(Ticket.id))) or 0
    return f"{settings.default_project_key}-{count + 1}"


def _add_event(
    db: Session,
    *,
    ticket_id: int,
    event_type: str,
    actor: str,
    field_name: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
) -> TicketEvent:
    event = TicketEvent(
        ticket_id=ticket_id,
        event_type=event_type,
        actor=actor,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
    )
    db.add(event)
    return event


def create_ticket(db: Session, payload: TicketCreate) -> Ticket:
    ticket = Ticket(
        key=_next_ticket_key(db),
        title=payload.title,
        description=payload.description,
        priority=payload.priority.value if isinstance(payload.priority, TicketPriority) else str(payload.priority),
        assignee=payload.assignee,
        reporter=payload.reporter,
        status=TicketStatus.OPEN.value,
    )
    db.add(ticket)
    db.flush()

    _add_event(
        db,
        ticket_id=ticket.id,
        event_type="ticket_created",
        actor=payload.reporter,
        new_value=f"{ticket.key} created",
    )

    db.commit()
    db.refresh(ticket)
    logger.info("Created ticket key=%s id=%s", ticket.key, ticket.id)
    return ticket


def list_tickets(
    db: Session,
    *,
    status: str | None = None,
    priority: str | None = None,
    assignee: str | None = None,
    search: str | None = None,
) -> list[Ticket]:
    stmt = select(Ticket).order_by(Ticket.created_at.desc())

    if status:
        stmt = stmt.where(Ticket.status == status)
    if priority:
        stmt = stmt.where(Ticket.priority == priority)
    if assignee:
        stmt = stmt.where(Ticket.assignee == assignee)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            or_(
                Ticket.key.ilike(like),
                Ticket.title.ilike(like),
                Ticket.description.ilike(like),
            )
        )

    return list(db.scalars(stmt).all())


def get_ticket(db: Session, ticket_id: int) -> Ticket | None:
    stmt = (
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .options(
            selectinload(Ticket.comments),
            selectinload(Ticket.events),
        )
    )
    return db.scalar(stmt)


def update_ticket(db: Session, ticket: Ticket, payload: TicketUpdate) -> Ticket:
    updates = payload.model_dump(exclude_unset=True)
    actor = updates.pop("actor", "system")

    field_map = {
        "title": "title",
        "description": "description",
        "priority": "priority",
        "assignee": "assignee",
        "reporter": "reporter",
        "status": "status",
    }

    for field, attr in field_map.items():
        if field not in updates:
            continue

        new_value = updates[field]
        if hasattr(new_value, "value"):
            new_value = new_value.value

        old_value = getattr(ticket, attr)
        if old_value == new_value:
            continue

        setattr(ticket, attr, new_value)
        _add_event(
            db,
            ticket_id=ticket.id,
            event_type="field_updated",
            actor=actor,
            field_name=field,
            old_value=None if old_value is None else str(old_value),
            new_value=None if new_value is None else str(new_value),
        )

    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def transition_ticket(db: Session, ticket: Ticket, payload: TicketTransitionRequest) -> Ticket:
    old_status = ticket.status
    new_status = payload.status.value if isinstance(payload.status, TicketStatus) else str(payload.status)

    if old_status == new_status:
        return ticket

    allowed = {
        TicketStatus.OPEN.value: {TicketStatus.IN_PROGRESS.value, TicketStatus.CLOSED.value},
        TicketStatus.IN_PROGRESS.value: {TicketStatus.RESOLVED.value, TicketStatus.OPEN.value},
        TicketStatus.RESOLVED.value: {TicketStatus.CLOSED.value, TicketStatus.IN_PROGRESS.value},
        TicketStatus.CLOSED.value: {TicketStatus.OPEN.value},
    }

    if new_status not in allowed.get(old_status, set()):
        raise ValueError(f"Invalid transition from '{old_status}' to '{new_status}'")

    ticket.status = new_status
    _add_event(
        db,
        ticket_id=ticket.id,
        event_type="status_transition",
        actor=payload.actor,
        field_name="status",
        old_value=old_status,
        new_value=new_status,
    )

    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def add_comment(db: Session, ticket: Ticket, payload: CommentCreate) -> Comment:
    comment = Comment(ticket_id=ticket.id, author=payload.author, body=payload.body)
    db.add(comment)
    db.flush()

    _add_event(
        db,
        ticket_id=ticket.id,
        event_type="comment_added",
        actor=payload.author,
        field_name="comment",
        new_value=payload.body[:500],
    )

    db.commit()
    db.refresh(comment)
    return comment