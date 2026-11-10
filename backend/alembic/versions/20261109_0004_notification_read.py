"""Notifications: mark as read, and allow ones not about a shift (HH-27)

Revision ID: 0004_notification_read
Revises: 20261105_0003
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_notification_read"
down_revision: str | None = "20261105_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("notifications") as batch:
        # When the reader opened it; NULL means unread, which is what the bell counts.
        batch.add_column(sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))
        # A role or rule change is not about a shift, so this can be empty.
        batch.alter_column("shift_id", existing_type=sa.Integer(), nullable=True)
    op.create_index(
        "ix_notifications_user_id_read_at", "notifications", ["user_id", "read_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_id_read_at", table_name="notifications")
    with op.batch_alter_table("notifications") as batch:
        batch.alter_column("shift_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("read_at")
