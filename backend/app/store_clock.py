"""The stores' own time zone, and converting between it and the UTC the database holds.

Kept out of the services so anything can use it without importing one of them: the audit
history and the reports both need store-local days, and ``app/services/shifts.py`` would
otherwise import them while they import it.
"""

from datetime import UTC, date, datetime, time, timedelta, timezone

# Every store in the chain is in India, so one zone is enough. A store opening elsewhere
# would make this a column on Store instead.
STORE_TIMEZONE = timezone(timedelta(hours=5, minutes=30), "IST")


def store_time(day: date, at: time) -> datetime:
    """A store-local date and time as a UTC datetime."""
    return datetime.combine(day, at, STORE_TIMEZONE).astimezone(UTC)


def start_of_day(day: date) -> datetime:
    """Midnight at the start of that store-local day, in UTC."""
    return store_time(day, time(0))


def end_of_day(day: date) -> datetime:
    """Midnight at the end of that store-local day, in UTC (exclusive)."""
    return start_of_day(day) + timedelta(days=1)
