"""In-app notifications for volunteer shift changes."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_volunteer
from app.db.session import get_db
from app.models import Notification, User

router = APIRouter(tags=["notifications"])


class Notice(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shift_id: int
    message: str
    created_at: datetime


@router.get("/notifications", response_model=list[Notice])
def notifications(user: User = Depends(require_volunteer), db: Session = Depends(get_db)):
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.id.desc())
        )
    )
