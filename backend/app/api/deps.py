"""Dependencies shared by the endpoints.

Every endpoint except health and sign-in must say who may call it (HH-12, deny by default;
``tests/test_access.py`` fails for any route that doesn't):

    @router.post("/shifts", status_code=201)
    def post_shift(body: ShiftIn, user: User = Depends(require_manager), ...):
        store = access.get_store_in_scope(db, user, body.store_id)  # 403 if not their store

    @router.patch("/shifts/{shift_id}", dependencies=[Depends(require_manager)])
    def edit_shift(body: ShiftEdit, shift: Shift = Depends(shift_in_scope), ...):

``require_role(...)`` gives 403 FORBIDDEN to any other role. ``shift_in_scope`` and
``signup_in_scope`` load the item from the path id and give 404 if it doesn't exist and 403
STORE_FORBIDDEN if it belongs to another store (rules in ``app/services/access.py``).
"""

from collections.abc import Callable

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import AuthSession, Shift, SignUp, User, UserRole
from app.services import access, auth

bearer = HTTPBearer(auto_error=False)


def get_current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> AuthSession:
    return auth.authenticate(db, credentials.credentials if credentials else None)


def get_current_user(session: AuthSession = Depends(get_current_session)) -> User:
    return session.user


def require_role(*roles: UserRole) -> Callable[..., User]:
    """A dependency that lets only these roles through and returns the signed-in user."""
    if not roles:
        raise ValueError("require_role needs at least one role")
    allowed = frozenset(roles)

    def dependency(user: User = Depends(get_current_user)) -> User:
        access.ensure_role(user, allowed)
        return user

    dependency.allowed_roles = allowed  # read by the route check in tests/test_access.py
    return dependency


# The combinations the SAD's API table uses. Add one here rather than in an endpoint module.
require_volunteer = require_role(UserRole.VOLUNTEER)
require_manager = require_role(UserRole.STORE_MANAGER)
require_admin = require_role(UserRole.ADMIN)
require_manager_or_admin = require_role(UserRole.STORE_MANAGER, UserRole.ADMIN)
require_any_role = require_role(*UserRole)


def shift_in_scope(
    shift_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Shift:
    """The shift named in the path, if the user may change it. Pair it with a role check."""
    return access.get_shift_in_scope(db, user, shift_id)


def signup_in_scope(
    signup_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SignUp:
    """The sign-up named in the path, if the user may act on it. Pair it with a role check."""
    return access.get_signup_in_scope(db, user, signup_id)
