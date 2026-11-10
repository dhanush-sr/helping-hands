"""The background job that sends shift reminders (HH-28).

APScheduler runs ``send_reminders`` every few minutes inside the API process. The job
holds its own database session, and ``send_due`` is safe to run again, so a missed or
repeated run costs nothing.

It is off during tests and can be turned off anywhere with ``HH_REMINDERS_ENABLED=false``;
the tests call ``send_due`` directly with a fixed clock instead.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_settings
from app.db.session import SessionLocal
from app.services import reminders

log = logging.getLogger(__name__)


def send_reminders() -> None:
    """One pass of the job. Never raises, so a bad run cannot stop the schedule."""
    try:
        with SessionLocal() as db:
            sent = reminders.send_due(db)
        if sent:
            log.info("Sent %d shift reminders", sent)
    except Exception:  # noqa: BLE001 - the scheduler must survive any failure
        log.exception("Sending shift reminders failed")


def start() -> BackgroundScheduler | None:
    """Start the schedule, or return None when reminders are switched off."""
    settings = get_settings()
    if not settings.reminders_enabled:
        return None
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        send_reminders,
        "interval",
        minutes=settings.reminder_interval_minutes,
        id="shift-reminders",
        # If the process was busy or asleep, run once on waking rather than catching up.
        coalesce=True,
        max_instances=1,
        next_run_time=None,
    )
    scheduler.start()
    log.info("Shift reminders every %d minutes", settings.reminder_interval_minutes)
    return scheduler
