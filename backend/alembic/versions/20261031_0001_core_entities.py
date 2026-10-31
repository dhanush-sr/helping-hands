"""Core entities: users, stores, busy periods, shifts, sign-ups, settings (HH-9)

Revision ID: 0001_core_entities
Revises:
Create Date: 2026-10-31

Attendance, notifications and audit events come in Sprint 2 migrations.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_core_entities"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

USER_ROLES = ("VOLUNTEER", "STORE_MANAGER", "ADMIN")
SHIFT_STATUSES = ("OPEN", "FILLED", "CANCELLED", "COMPLETED")
SIGNUP_STATUSES = ("REQUESTED", "CONFIRMED", "DECLINED", "WITHDRAWN")

# Defaults for the admin-editable rules (kept here, not imported, so this migration never
# changes when the app code does).
DEFAULT_SETTINGS = [
    {
        "key": "weekly_hour_limit",
        "value": 8,
        "description": "Most hours a volunteer can hold per week (Monday to Sunday)",
    },
    {
        "key": "min_notice_hours",
        "value": 12,
        "description": "Sign-ups close this many hours before a shift starts",
    },
    {
        "key": "withdrawal_cutoff_hours",
        "value": 24,
        "description": "Volunteers can withdraw until this many hours before",
    },
]


def _enum(values: tuple[str, ...], name: str) -> sa.Enum:
    # Stored as VARCHAR + CHECK constraint (works the same on SQLite and PostgreSQL).
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=20)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", _enum(USER_ROLES, "role"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("failed_login_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )

    op.create_table(
        "stores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=False),
        sa.Column("manager_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["manager_id"],
            ["users.id"],
            name=op.f("fk_stores_manager_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stores")),
        sa.UniqueConstraint("name", name=op.f("uq_stores_name")),
    )
    op.create_index(op.f("ix_stores_manager_id"), "stores", ["manager_id"])

    op.create_table(
        "busy_periods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "end_date >= start_date", name=op.f("ck_busy_periods_end_not_before_start")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_busy_periods")),
    )

    op.create_table(
        "shifts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("busy_period_id", sa.Integer(), nullable=True),
        sa.Column("task", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slots", sa.Integer(), nullable=False),
        sa.Column(
            "status", _enum(SHIFT_STATUSES, "status"), server_default="OPEN", nullable=False
        ),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_shifts_ends_after_starts")),
        sa.CheckConstraint("slots >= 1", name=op.f("ck_shifts_slots_at_least_one")),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
            name=op.f("fk_shifts_store_id_stores"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["busy_period_id"],
            ["busy_periods.id"],
            name=op.f("fk_shifts_busy_period_id_busy_periods"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_shifts_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shifts")),
    )
    op.create_index(op.f("ix_shifts_store_id"), "shifts", ["store_id"])
    op.create_index(op.f("ix_shifts_busy_period_id"), "shifts", ["busy_period_id"])
    op.create_index("ix_shifts_status_starts_at", "shifts", ["status", "starts_at"])

    op.create_table(
        "signups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shift_id", sa.Integer(), nullable=False),
        sa.Column("volunteer_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            _enum(SIGNUP_STATUSES, "status"),
            server_default="REQUESTED",
            nullable=False,
        ),
        sa.Column("decided_by_id", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["shift_id"],
            ["shifts.id"],
            name=op.f("fk_signups_shift_id_shifts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["volunteer_id"],
            ["users.id"],
            name=op.f("fk_signups_volunteer_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_id"],
            ["users.id"],
            name=op.f("fk_signups_decided_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signups")),
        sa.UniqueConstraint(
            "shift_id", "volunteer_id", name=op.f("uq_signups_shift_id_volunteer_id")
        ),
    )
    op.create_index(op.f("ix_signups_volunteer_id"), "signups", ["volunteer_id"])

    settings_table = op.create_table(
        "settings",
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("value > 0", name=op.f("ck_settings_value_positive")),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name=op.f("fk_settings_updated_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_settings")),
    )
    op.bulk_insert(settings_table, DEFAULT_SETTINGS)


def downgrade() -> None:
    op.drop_table("settings")
    op.drop_index(op.f("ix_signups_volunteer_id"), table_name="signups")
    op.drop_table("signups")
    op.drop_index("ix_shifts_status_starts_at", table_name="shifts")
    op.drop_index(op.f("ix_shifts_busy_period_id"), table_name="shifts")
    op.drop_index(op.f("ix_shifts_store_id"), table_name="shifts")
    op.drop_table("shifts")
    op.drop_table("busy_periods")
    op.drop_index(op.f("ix_stores_manager_id"), table_name="stores")
    op.drop_table("stores")
    op.drop_table("users")
