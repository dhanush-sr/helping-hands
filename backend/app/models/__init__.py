"""All ORM models. Importing this package registers every table on ``Base.metadata``
(Alembic's env.py relies on that).

Attendance, Notification and AuditEvent are added in Sprint 2.
"""

from app.db.base import Base
from app.models.busy_period import BusyPeriod
from app.models.enums import ShiftStatus, SignUpStatus, UserRole
from app.models.setting import DEFAULT_SETTINGS, Setting
from app.models.shift import Shift
from app.models.signup import SignUp
from app.models.store import Store
from app.models.user import User

__all__ = [
    "DEFAULT_SETTINGS",
    "Base",
    "BusyPeriod",
    "Setting",
    "Shift",
    "ShiftStatus",
    "SignUp",
    "SignUpStatus",
    "Store",
    "User",
    "UserRole",
]
