from sqlalchemy.orm import Session

from app.crud import add_comment, create_ticket, transition_ticket
from app.db import SessionLocal
from app.schemas import CommentCreate, TicketCreate, TicketTransitionRequest


def run() -> None:
    db: Session = SessionLocal()
    try:
        t1 = create_ticket(
            db,
            TicketCreate(
                title="Foundry agent cannot retrieve ticket comments",
                description="Investigate MCP tool flow for comment retrieval.",
                priority="High",
                assignee="agent.team",
                reporter="seed",
            ),
        )
        add_comment(db, t1, CommentCreate(author="seed", body="Initial triage created this ticket."))

        t2 = create_ticket(
            db,
            TicketCreate(
                title="Test workflow transition behavior",
                description="Validate Open -> In Progress -> Resolved path.",
                priority="Medium",
                assignee="qa.agent",
                reporter="seed",
            ),
        )
        transition_ticket(db, t2, TicketTransitionRequest(status="In Progress", actor="seed"))
    finally:
        db.close()


if __name__ == "__main__":
    run()