"""Sign-ups.

HH-17 adds ``POST /api/v1/shifts/{shiftId}/signups`` for volunteers, as in the SAD:

    POST /api/v1/shifts/845/signups      (no body)
    201 {"signUpId": 12, "shiftId": 845, "status": "REQUESTED"}

Refused with 409 and the eligibility code (``SHIFT_FULL``, ``SHIFT_CANCELLED``,
``SHIFT_STARTED``, ``STORE_INACTIVE``; HH-18 adds ``NOTICE``, ``CLASH``, ``WEEKLY_LIMIT``),
409 ``ALREADY_SIGNED_UP`` for a second sign-up, 404 ``SHIFT_NOT_FOUND`` for an unknown shift
and 403 ``FORBIDDEN`` for any role other than volunteer.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_volunteer
from app.api.v1.shifts import CamelModel
from app.db.session import get_db
from app.models import SignUpStatus, User
from app.services import signups

router = APIRouter(tags=["signups"])


class SignUpCreated(CamelModel):
    sign_up_id: int
    shift_id: int
    status: SignUpStatus


@router.post(
    "/shifts/{shift_id}/signups",
    response_model=SignUpCreated,
    response_model_by_alias=True,
    status_code=201,
)
def sign_up(
    shift_id: int, user: User = Depends(require_volunteer), db: Session = Depends(get_db)
) -> SignUpCreated:
    signup = signups.sign_up(db, user, shift_id)
    return SignUpCreated(sign_up_id=signup.id, shift_id=signup.shift_id, status=signup.status)


@router.post("/signups/{signup_id}/withdraw", response_model=SignUpCreated)
def withdraw(
    signup_id: int, user: User = Depends(require_volunteer), db: Session = Depends(get_db)
) -> SignUpCreated:
    signup = signups.withdraw(db, user, signup_id)
    return SignUpCreated(sign_up_id=signup.id, shift_id=signup.shift_id, status=signup.status)
