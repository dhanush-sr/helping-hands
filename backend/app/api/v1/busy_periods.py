"""Busy periods (HH-13, HH-F-005).

| Method and path | Who |
|---|---|
| GET /api/v1/busy-periods | everyone signed in |
| POST /api/v1/busy-periods | admin |

Managers pick a busy period when posting a shift; volunteers filter open shifts by it.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_any_role
from app.db.session import get_db
from app.models import BusyPeriod
from app.services import stores

router = APIRouter(prefix="/busy-periods", tags=["busy periods"])


class BusyPeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    start_date: date
    end_date: date


class BusyPeriodIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    start_date: date
    end_date: date


@router.get("", response_model=list[BusyPeriodOut], dependencies=[Depends(require_any_role)])
def list_busy_periods(db: Session = Depends(get_db)) -> list[BusyPeriod]:
    return stores.list_busy_periods(db)


@router.post(
    "", response_model=BusyPeriodOut, status_code=201, dependencies=[Depends(require_admin)]
)
def create_busy_period(body: BusyPeriodIn, db: Session = Depends(get_db)) -> BusyPeriod:
    return stores.create_busy_period(db, body.name, body.start_date, body.end_date)
