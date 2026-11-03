"""The admin-editable volunteering rules (HH-F-006), read from the ``settings`` table.

The first migration inserts the rows with the defaults in ``app.models.setting``. Services
read a rule through ``value`` instead of hard-coding a number, so when HH-20 adds the admin
screen that changes a rule, the sign-up and withdrawal checks follow it straight away.
"""

from sqlalchemy.orm import Session

from app.models import DEFAULT_SETTINGS, Setting


def value(db: Session, key: str) -> int:
    """The current value of a rule, falling back to its default if the row is missing."""
    setting = db.get(Setting, key)
    if setting is not None:
        return setting.value
    return DEFAULT_SETTINGS[key][0]
