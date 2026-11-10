"""Audit events: say what kind of thing each one is about (HH-33)

Revision ID: 0005_audit_entity_type
Revises: 0004_notification_read
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_audit_entity_type"
down_revision: str | None = "0004_notification_read"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The SRS records an entity type beside the id, so "42" is readably a shift or a sign-up.
# Existing rows get theirs from the action they already carry.
BACKFILL = [
    ("SHIFT", "SHIFT_%"),
    ("SIGNUP", "SIGNUP_%"),
    ("SIGNUP", "ATTENDANCE_%"),
    ("USER", "USER_%"),
]


def upgrade() -> None:
    with op.batch_alter_table("audit_events") as batch:
        batch.add_column(
            sa.Column(
                "entity_type",
                sa.String(length=20),
                nullable=False,
                server_default="OTHER",
            )
        )
    events = sa.table(
        "audit_events", sa.column("entity_type", sa.String), sa.column("action", sa.String)
    )
    for entity_type, pattern in BACKFILL:
        op.execute(
            events.update().where(events.c.action.like(pattern)).values(entity_type=entity_type)
        )
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    with op.batch_alter_table("audit_events") as batch:
        batch.drop_column("entity_type")
