"""add SLA fields

Revision ID: b2c3d4e5f6a7
Revises: a1f2c3d4e5f6
Create Date: 2026-08-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1f2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("target_resolution_time", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tickets", sa.Column("sla_status", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "sla_status")
    op.drop_column("tickets", "target_resolution_time")