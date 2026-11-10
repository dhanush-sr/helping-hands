"""Coverage and volunteer reports (HH-32: HH-F-021, HH-F-022).

| Method and path | Who |
|---|---|
| GET /api/v1/reports/{name} | store manager (their own store) or admin |
| GET /api/v1/reports/{name}.csv | the same rows as a download |

``name`` is coverage, hours or no-shows. All three take the same filters: ``storeId``,
``busyPeriodId``, ``since`` and ``until``. Both routes build their rows the same way, so
the download and the page can never disagree.
"""

import csv
import io
from dataclasses import asdict, fields
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import require_manager_or_admin
from app.db.session import get_db
from app.errors import ApiError
from app.models import User
from app.services import reports

router = APIRouter(prefix="/reports", tags=["reports"])

# Each report's builder and the row it returns; the row's fields are the CSV columns.
REPORTS = {
    "coverage": (reports.coverage, reports.CoverageRow),
    "hours": (reports.hours, reports.VolunteerRow),
    "no-shows": (reports.no_shows, reports.NoShowRow),
}


def build(
    name: str,
    viewer: User,
    db: Session,
    store_id: int | None,
    busy_period_id: int | None,
    since: date | None,
    until: date | None,
) -> tuple[list, list[str]]:
    """The report's rows and its column names, with the viewer's store scope applied."""
    entry = REPORTS.get(name)
    if entry is None:
        raise ApiError(
            404, "UNKNOWN_REPORT", f"No report called {name}. Try: {', '.join(REPORTS)}."
        )
    builder, row_type = entry
    filters = reports.Filters(
        store_id=store_id, busy_period_id=busy_period_id, since=since, until=until
    )
    reports.check_filters(db, filters)
    columns = [field.name for field in fields(row_type)]
    store_ids = reports.visible_stores(db, viewer, filters.store_id)
    if not store_ids:  # a manager with no store yet
        return [], columns
    return builder(db, store_ids, filters), columns


# Registered before /{name}, which would otherwise capture "coverage.csv" as the name.
@router.get("/{name}.csv")
def report_csv(
    name: str,
    store_id: int | None = Query(default=None, alias="storeId"),
    busy_period_id: int | None = Query(default=None, alias="busyPeriodId"),
    since: date | None = Query(default=None),
    until: date | None = Query(default=None),
    user: User = Depends(require_manager_or_admin),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """The same rows as a spreadsheet. An empty report still sends its header row."""
    rows, columns = build(name, user, db, store_id, busy_period_id, since, until)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in rows:
        values = asdict(row)
        writer.writerow([values[column] for column in columns])

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
    )


@router.get("/{name}")
def report(
    name: str,
    store_id: int | None = Query(default=None, alias="storeId"),
    busy_period_id: int | None = Query(default=None, alias="busyPeriodId"),
    since: date | None = Query(default=None),
    until: date | None = Query(default=None),
    user: User = Depends(require_manager_or_admin),
    db: Session = Depends(get_db),
) -> dict:
    rows, columns = build(name, user, db, store_id, busy_period_id, since, until)
    return {"report": name, "columns": columns, "rows": [asdict(row) for row in rows]}
