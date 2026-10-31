"""Stores and their managers (HH-13, HH-F-004).

| Method and path | Who |
|---|---|
| GET /api/v1/stores | admin (all stores) or store manager (their own active stores) |
| POST /api/v1/stores | admin |
| PATCH /api/v1/stores/{store_id} | admin |
| GET /api/v1/store-managers | admin, for the "assign manager" choice |
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_manager_or_admin
from app.db.session import get_db
from app.models import Store, User
from app.services import stores

router = APIRouter(tags=["stores"])

StoreName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Location = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class ManagerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str


class StoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location: str
    is_active: bool
    manager: ManagerOut | None


class StoreIn(BaseModel):
    name: StoreName
    location: Location
    manager_id: int | None = None


class StoreChange(BaseModel):
    """Send only the fields to change. ``"manager_id": null`` clears the manager."""

    name: StoreName | None = None
    location: Location | None = None
    manager_id: int | None = None
    is_active: bool | None = None


@router.get("/stores", response_model=list[StoreOut])
def list_stores(
    user: User = Depends(require_manager_or_admin), db: Session = Depends(get_db)
) -> list[Store]:
    return stores.list_stores(db, user)


@router.post(
    "/stores",
    response_model=StoreOut,
    status_code=201,
    dependencies=[Depends(require_admin)],
)
def create_store(body: StoreIn, db: Session = Depends(get_db)) -> Store:
    return stores.create_store(db, body.name, body.location, body.manager_id)


@router.patch(
    "/stores/{store_id}", response_model=StoreOut, dependencies=[Depends(require_admin)]
)
def update_store(store_id: int, body: StoreChange, db: Session = Depends(get_db)) -> Store:
    sent = body.model_fields_set
    return stores.update_store(
        db,
        store_id,
        name=body.name,
        location=body.location,
        manager_id=body.manager_id if "manager_id" in sent else stores.KEEP,
        is_active=body.is_active,
    )


@router.get(
    "/store-managers", response_model=list[ManagerOut], dependencies=[Depends(require_admin)]
)
def list_store_managers(db: Session = Depends(get_db)) -> list[User]:
    return stores.list_store_managers(db)
