"""engineers table + ticket assignment

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED_ENGINEERS = [
    {"name": "Alice Chen", "email": "alice.chen@tracepulse.dev", "slack_handle": "@alice"},
    {"name": "Bob Verma", "email": "bob.verma@tracepulse.dev", "slack_handle": "@bob"},
    {"name": "Carol Diaz", "email": "carol.diaz@tracepulse.dev", "slack_handle": "@carol"},
]


def upgrade() -> None:
    op.create_table(
        "engineers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("slack_handle", sa.String(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "tickets",
        sa.Column("assigned_engineer_id", sa.Integer(), sa.ForeignKey("engineers.id"), nullable=True),
    )
    # Minimal seed data so there is something to assign to for testing.
    engineers = sa.table(
        "engineers",
        sa.column("name", sa.String),
        sa.column("email", sa.String),
        sa.column("slack_handle", sa.String),
        sa.column("active", sa.Boolean),
    )
    op.bulk_insert(engineers, [dict(e, active=True) for e in SEED_ENGINEERS])


def downgrade() -> None:
    op.drop_column("tickets", "assigned_engineer_id")
    op.drop_table("engineers")