"""Shifts (help requests).

HH-15 adds ``POST /api/v1/shifts`` for store managers, shaped as in the SAD (camelCase JSON,
store-local date and times):

    request  {"storeId": 1, "busyPeriodId": 1, "date": "2026-11-08", "startTime": "10:00",
              "endTime": "14:00", "task": "Billing", "slotsNeeded": 3, "notes": "Festive rush"}
    response 201 {"shiftId": 845, "status": "OPEN", "freeSlots": 3}

Browsing (GET /api/v1/shifts, HH-16) is added to this module later.
"""

from datetime import date, time
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from app.api.deps import require_manager
from app.db.session import get_db
from app.models import ShiftStatus, User
from app.services import shifts

router = APIRouter(prefix="/shifts", tags=["shifts"])


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ShiftIn(CamelModel):
    store_id: int
    busy_period_id: int | None = None
    date: date
    start_time: time
    end_time: time
    task: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    # Range checked by the service so a bad number gets 400 INVALID_SLOTS, as HH-15 asks.
    slots_needed: int
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = (
        Field(default=None)
    )


class ShiftCreated(CamelModel):
    shift_id: int
    status: ShiftStatus
    free_slots: int


@router.post("", response_model=ShiftCreated, response_model_by_alias=True, status_code=201)
def post_shift(
    body: ShiftIn, user: User = Depends(require_manager), db: Session = Depends(get_db)
) -> ShiftCreated:
    shift = shifts.create_shift(
        db,
        user,
        store_id=body.store_id,
        day=body.date,
        start_time=body.start_time,
        end_time=body.end_time,
        task=body.task,
        slots=body.slots_needed,
        busy_period_id=body.busy_period_id,
        notes=body.notes,
    )
    return ShiftCreated(shift_id=shift.id, status=shift.status, free_slots=shifts.free_slots(shift))
