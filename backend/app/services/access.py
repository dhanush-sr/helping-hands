"""Who may do what (HH-12: HH-F-002, HH-SR-004).

Two checks, both made on the server for every protected request, both denying by default:

- Role: every endpoint names the roles that may call it (``require_role`` in
  ``app/api/deps.py``). Any other role gets 403 ``FORBIDDEN`` before the request body is read.
- Store scope: a store manager may only change their own store and that store's shifts and
  sign-ups; anything else is 403 ``STORE_FORBIDDEN``. Admins work across every store.
  Volunteers have no store, so they are always out of store scope; for sign-ups they may only
  touch their own.

An id that does not exist gives 404; one that exists but is out of scope gives 403 (SAD 4.3).
"""

from collections.abc import Collection

from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Shift, SignUp, Store, User, UserRole


def forbidden(message: str = "You don't have permission to do this.") -> ApiError:
    return ApiError(403, "FORBIDDEN", message)


def store_forbidden() -> ApiError:
    return ApiError(
        403, "STORE_FORBIDDEN", "You can only manage your own store's shifts and sign-ups."
    )


def ensure_role(user: User, allowed: Collection[UserRole]) -> None:
    if user.role not in allowed:
        raise forbidden()


def can_manage_store(user: User, store: Store) -> bool:
    if user.role == UserRole.ADMIN:
        return True
    return user.role == UserRole.STORE_MANAGER and store.manager_id == user.id


def ensure_store_scope(user: User, store: Store) -> None:
    if not can_manage_store(user, store):
        raise store_forbidden()


def get_store_in_scope(db: Session, user: User, store_id: int) -> Store:
    """The store, if this user may change it. Use it for a store id sent in a request body."""
    store = db.get(Store, store_id)
    if store is None:
        raise ApiError(404, "STORE_NOT_FOUND", "No store with that id.")
    ensure_store_scope(user, store)
    return store


def get_shift_in_scope(db: Session, user: User, shift_id: int) -> Shift:
    """The shift, if this user may change it (its store's manager, or an admin)."""
    shift = db.get(Shift, shift_id)
    if shift is None:
        raise ApiError(404, "SHIFT_NOT_FOUND", "No shift with that id.")
    ensure_store_scope(user, shift.store)
    return shift


def get_signup_in_scope(db: Session, user: User, signup_id: int) -> SignUp:
    """The sign-up, if this user may act on it.

    Volunteers: only their own. Store managers: only sign-ups for their store's shifts.
    Admins: any.
    """
    signup = db.get(SignUp, signup_id)
    if signup is None:
        raise ApiError(404, "SIGNUP_NOT_FOUND", "No sign-up with that id.")
    if user.role == UserRole.VOLUNTEER:
        if signup.volunteer_id != user.id:
            raise forbidden("You can only change your own sign-ups.")
    else:
        ensure_store_scope(user, signup.shift.store)
    return signup
