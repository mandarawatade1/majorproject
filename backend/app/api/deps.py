"""Shared route dependencies: who is asking, and may they.

Two rules are worth stating because getting either wrong is silent.

**The database is the authority on whether an account still exists.** The token
carries a role so ordinary checks need no query, but the user is loaded and
`is_active` is re-checked on every authenticated request. A token issued before
an account was disabled must stop working, and a role embedded in a signed blob
cannot know that.

**Anonymous is a valid state, not an error.** The portal is public: reads and
Ask PCE work with no credentials at all. `optional_user` exists so a route can
personalise for a signed-in user without demanding one, and only `require_admin`
actually refuses.
"""

from __future__ import annotations

import uuid
from typing import Annotated

import jwt
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.interaction import User
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token

logger = get_logger(__name__)

# auto_error=False: a missing header must reach `optional_user` as "anonymous"
# rather than becoming a 403 before the route is entered.
_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def _user_from_token(token: str, db: Session) -> User | None:
    try:
        payload = decode_token(token, expected_type="access")
    except jwt.InvalidTokenError:
        # Expired, malformed, wrong type, wrong signature — all the same to a
        # caller. Distinguishing them tells an attacker which part to fix.
        return None

    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except (ValueError, KeyError):
        return None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def optional_user(db: DbSession, credentials: Credentials = None) -> User | None:
    """The signed-in user, or None. Never raises."""
    if credentials is None or not credentials.credentials:
        return None
    return _user_from_token(credentials.credentials, db)


def current_user(db: DbSession, credentials: Credentials = None) -> User:
    """The signed-in user, or 401."""
    if credentials is None or not credentials.credentials:
        raise _UNAUTHENTICATED
    user = _user_from_token(credentials.credentials, db)
    if user is None:
        raise _UNAUTHENTICATED
    return user


def require_admin(
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> User:
    """The signed-in user, if they are an administrator. Otherwise 403.

    A refused attempt is logged with the path and the account that made it.
    Administrative surface is the part of this system worth attacking, and an
    unlogged refusal leaves no trace that anyone tried.
    """
    if user.role is not UserRole.ADMIN:
        logger.warning(
            "admin_access_denied",
            user_id=str(user.id),
            role=user.role.value,
            path=request.url.path,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="this endpoint requires an administrator account",
        )
    return user


CurrentUser = Annotated[User, Depends(current_user)]
OptionalUser = Annotated[User | None, Depends(optional_user)]
AdminUser = Annotated[User, Depends(require_admin)]

__all__ = [
    "AdminUser",
    "CurrentUser",
    "OptionalUser",
    "current_user",
    "optional_user",
    "require_admin",
]
