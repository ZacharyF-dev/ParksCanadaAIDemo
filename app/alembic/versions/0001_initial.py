"""initial

Revision ID: 0001_initial
Revises: None
Create Date: 2026-07-03 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="Open"),
        sa.Column("priority", sa.String(length=32), nullable=False, server_default="Medium"),
        sa.Column("assignee", sa.String(length=255), nullable=True),
        sa.Column("reporter", sa.String(length=255), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
    )
    op.create_index("ix_tickets_id", "tickets", ["id"], unique=False)
    op.create_index("ix_tickets_key", "tickets", ["key"], unique=True)

    op.create_table(
        "comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=False, server_default="system"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_comments_ticket_id", "comments", ["ticket_id"], unique=False)

    op.create_table(
        "ticket_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False, server_default="system"),
        sa.Column("field_name", sa.String(length=64), nullable=True),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_ticket_events_ticket_id", "ticket_events", ["ticket_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ticket_events_ticket_id", table_name="ticket_events")
    op.drop_table("ticket_events")
    op.drop_index("ix_comments_ticket_id", table_name="comments")
    op.drop_table("comments")
    op.drop_index("ix_tickets_key", table_name="tickets")
    op.drop_index("ix_tickets_id", table_name="tickets")
    op.drop_table("tickets")