"""add triage fields and status workflow

Revision ID: a1f2c3d4e5f6
Revises: 332811e1e970
Create Date: 2026-08-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '332811e1e970'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("priority", sa.String(), nullable=True))
    op.add_column("tickets", sa.Column("ai_severity", sa.String(), nullable=True))
    op.add_column("tickets", sa.Column("issue_type", sa.String(), nullable=True))
    op.add_column("tickets", sa.Column("team", sa.String(), nullable=True))
    op.add_column(
        "tickets",
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
    )
    op.create_check_constraint(
        "ck_tickets_status", "tickets", "status IN ('open', 'in_progress', 'resolved', 'closed')"
    )
    # Backfill: V1 tickets that already have a resolution count as resolved.
    op.execute("UPDATE tickets SET status = 'resolved' WHERE resolution_text IS NOT NULL")
    op.alter_column("tickets", "status", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_tickets_status", "tickets", type_="check")
    op.drop_column("tickets", "status")
    op.drop_column("tickets", "team")
    op.drop_column("tickets", "issue_type")
    op.drop_column("tickets", "ai_severity")
    op.drop_column("tickets", "priority")