"""Remember which sign-ups have had their reminder (HH-28)

Revision ID: 0006_signup_reminders
Revises: 0005_audit_entity_type
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_signup_reminders"
down_revision: str | None = "0005_audit_entity_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("signups") as batch:
        # When the 24-hour reminder went out. Empty means it has not, which is what the
        # job looks for, so a restart or a second run never sends a second reminder.
        batch.add_column(sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("signups") as batch:
        batch.drop_column("reminded_at")
