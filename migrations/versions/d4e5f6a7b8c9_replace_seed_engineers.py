"""replace seed engineers with new roster

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


SEED_ENGINEERS = [
    {"name": "Brad Hawk", "email": "brad.hawk@tracepulse.dev", "slack_handle": "@brad.hawk"},
    {"name": "Shun Ying Lee", "email": "shun.ying.lee@tracepulse.dev", "slack_handle": "@shun.ying.lee"},
    {"name": "Dwayne Davis", "email": "dwayne.davis@tracepulse.dev", "slack_handle": "@dwayne.davis"},
    {"name": "Glen Kluger", "email": "glen.kluger@tracepulse.dev", "slack_handle": "@glen.kluger"},
    {"name": "Kadonashi Shotaro", "email": "kadonashi.shotaro@tracepulse.dev", "slack_handle": "@kadonashi.shotaro"},
    {"name": "Jake Hudson", "email": "jake.hudson@tracepulse.dev", "slack_handle": "@jake.hudson"},
    {"name": "Grimm", "email": "grimm@tracepulse.dev", "slack_handle": "@grimm"},
    {"name": "Chris Bowman", "email": "chris.bowman@tracepulse.dev", "slack_handle": "@chris.bowman"},
    {"name": "Dae-Suk Park", "email": "dae-suk.park@tracepulse.dev", "slack_handle": "@dae-suk.park"},
    {"name": "Tong Yoon Bulsook", "email": "tong.yoon.bulsook@tracepulse.dev", "slack_handle": "@tong.yoon.bulsook"},
    {"name": "Alex Steiner", "email": "alex.steiner@tracepulse.dev", "slack_handle": "@alex.steiner"},
    {"name": "Douglas McKinzie", "email": "douglas.mckinzie@tracepulse.dev", "slack_handle": "@douglas.mckinzie"},
    {"name": "Napalm", "email": "napalm@tracepulse.dev", "slack_handle": "@napalm"},
    {"name": "Golem", "email": "golem@tracepulse.dev", "slack_handle": "@golem"},
    {"name": "Lin Fong Lee", "email": "lin.fong.lee@tracepulse.dev", "slack_handle": "@lin.fong.lee"},
    {"name": "Shinkai", "email": "shinkai@tracepulse.dev", "slack_handle": "@shinkai"},
    {"name": "Bordin", "email": "bordin@tracepulse.dev", "slack_handle": "@bordin"},
    {"name": "Marshall Law", "email": "marshall.law@tracepulse.dev", "slack_handle": "@marshall.law"},
    {"name": "Paul Phoenix", "email": "paul.phoenix@tracepulse.dev", "slack_handle": "@paul.phoenix"},
]


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_SEED_NAMES = ["Alice Chen", "Bob Verma", "Carol Diaz"]


def upgrade() -> None:
    engineers = sa.table(
        "engineers",
        sa.column("name", sa.String),
        sa.column("email", sa.String),
        sa.column("slack_handle", sa.String),
        sa.column("active", sa.Boolean),
    )
    # Deactivate the original 3 seed engineers. They are NOT deleted so any
    # tickets already assigned to them keep their foreign key intact; the API
    # only lists/assigns active engineers.
    op.execute(
        engineers.update().where(engineers.c.name.in_(OLD_SEED_NAMES)).values(active=False)
    )
    # Idempotent: only insert names that don't already exist.
    conn = op.get_bind()
    existing = {row[0] for row in conn.execute(sa.select(engineers.c.name))}
    op.bulk_insert(
        engineers,
        [dict(e, active=True) for e in SEED_ENGINEERS if e["name"] not in existing],
    )


def downgrade() -> None:
    engineers = sa.table(
        "engineers",
        sa.column("name", sa.String),
        sa.column("active", sa.Boolean),
    )
    conn = op.get_bind()
    new_names = [e["name"] for e in SEED_ENGINEERS]
    conn.execute(
        engineers.delete().where(sa.and_(engineers.c.name.in_(new_names), engineers.c.active.is_(True)))
    )
    op.execute(
        engineers.update().where(engineers.c.name.in_(OLD_SEED_NAMES)).values(active=True)
    )
