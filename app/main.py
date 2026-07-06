from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import models  # noqa: F401
from app.config import get_settings
from app.crud import add_comment, create_ticket, get_ticket, list_tickets, transition_ticket, update_ticket
from app.db import Base, engine, get_db
from app.mcp import router as mcp_router
from app.schemas import CommentCreate, TicketCreate, TicketTransitionRequest, TicketUpdate, TicketDetail

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name)
app.include_router(mcp_router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}

@app.get("/api/tickets/{ticket_id}", response_model=TicketDetail)
def api_get_ticket(ticket_id: int, db: Session = Depends(get_db)) -> TicketDetail:
    ticket = get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return TicketDetail.model_validate(ticket)

@app.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    db: Session = Depends(get_db),
    status: str | None = None,
    priority: str | None = None,
    assignee: str | None = None,
    search: str | None = None,
) -> HTMLResponse:
    tickets = list_tickets(db, status=status, priority=priority, assignee=assignee, search=search)
    return templates.TemplateResponse(
    request=request,
    name="index.html",
    context={
        "tickets": tickets,
        "filters": {
            "status": status or "",
            "priority": priority or "",
            "assignee": assignee or "",
            "search": search or "",
        },
        "statuses": ["Open", "In Progress", "Resolved", "Closed"],
        "priorities": ["Low", "Medium", "High", "Critical"],
    },
)


@app.get("/tickets/new", response_class=HTMLResponse)
def new_ticket_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
    request=request,
    name="create_ticket.html",
    context={
        "priorities": ["Low", "Medium", "High", "Critical"],
    },
)


@app.post("/tickets/new")
def create_ticket_form(
    title: str = Form(...),
    description: str = Form(""),
    priority: str = Form("Medium"),
    assignee: str = Form(""),
    reporter: str = Form("system"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    ticket = create_ticket(
        db,
        TicketCreate(
            title=title,
            description=description,
            priority=priority,
            assignee=assignee or None,
            reporter=reporter,
        ),
    )
    return RedirectResponse(url=f"/tickets/{ticket.id}", status_code=303)


@app.get("/tickets/{ticket_id}", response_class=HTMLResponse)
def ticket_detail(ticket_id: int, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    ticket = get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return templates.TemplateResponse(
    request=request,
    name="ticket_detail.html",
    context={
        "ticket": ticket,
        "statuses": ["Open", "In Progress", "Resolved", "Closed"],
        "priorities": ["Low", "Medium", "High", "Critical"],
    },
)


@app.post("/tickets/{ticket_id}/update")
def update_ticket_form(
    ticket_id: int,
    title: str = Form(...),
    description: str = Form(""),
    priority: str = Form("Medium"),
    assignee: str = Form(""),
    reporter: str = Form("system"),
    actor: str = Form("system"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    ticket = get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    update_ticket(
        db,
        ticket,
        TicketUpdate(
            title=title,
            description=description,
            priority=priority,
            assignee=assignee or None,
            reporter=reporter,
            actor=actor,
        ),
    )
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=303)


@app.post("/tickets/{ticket_id}/transition")
def transition_ticket_form(
    ticket_id: int,
    status: str = Form(...),
    actor: str = Form("system"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    ticket = get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    try:
        transition_ticket(db, ticket, TicketTransitionRequest(status=status, actor=actor))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=303)


@app.post("/tickets/{ticket_id}/comments")
def add_comment_form(
    ticket_id: int,
    author: str = Form("system"),
    body: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    ticket = get_ticket(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    add_comment(db, ticket, CommentCreate(author=author, body=body))
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=303)