"""Status and role values. Stored as short strings with a CHECK constraint (portable to SQLite)."""

import enum


class UserRole(str, enum.Enum):
    VOLUNTEER = "VOLUNTEER"
    STORE_MANAGER = "STORE_MANAGER"
    ADMIN = "ADMIN"


class ShiftStatus(str, enum.Enum):
    OPEN = "OPEN"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"  # set once attendance is recorded for everyone (HH-30)


class SignUpStatus(str, enum.Enum):
    REQUESTED = "REQUESTED"
    CONFIRMED = "CONFIRMED"
    DECLINED = "DECLINED"
    WITHDRAWN = "WITHDRAWN"
