"""Authentication: log in, refresh, and find out who you are.

Scope is deliberately small. The portal is public — browsing and Ask PCE need
no account — so this exists to gate the administrative surface, not to manage a
user base. There is no registration endpoint: the only account is created by
`python -m app.seed admin` from configured credentials. Adding self-service
registration to a system whose only privileged role is `admin` would be adding
an attack surface for a feature nobody uses.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import jwt
from app.core.config import settings
from app.core.logging import get_logger
from app.models.interaction import User
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.security import (
    InsecureConfigurationError,
    create_token,
    decode_token,
    verify_password,
)

logger = get_logger(__name__)
router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    # A plain string rather than `EmailStr`, for two reasons. `EmailStr` needs
    # the `email-validator` package, which this project does not depend on and
    # which fails at import time rather than at first use — an undeclared
    # dependency that takes the whole application down on the next rebuild.
    # And validating the format here would answer a malformed address with 422
    # instead of the single 401 every other failure gets, which is a difference
    # an attacker can measure. The address is only ever compared to a stored
    # one; a non-address simply matches nothing.
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class Identity(BaseModel):
    id: str
    email: str
    full_name: str | None
    role: str
    is_active: bool


# One message for every failure. Distinguishing "no such account" from "wrong
# password" hands an attacker a free account-enumeration oracle, and the user
# who genuinely mistyped is no better off for knowing which half was wrong.
_REJECTED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="incorrect email or password",
    headers={"WWW-Authenticate": "Bearer"},
)


def _issue(user: User) -> TokenPair:
    try:
        access = create_token(user.id, user.role.value, "access")
        refresh = create_token(user.id, user.role.value, "refresh")
    except InsecureConfigurationError as exc:
        # Refusing to sign is the correct outcome, but it is an operator error,
        # not the caller's fault — hence 500 with the reason.
        logger.error("token_issue_refused", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/auth/login", response_model=TokenPair, summary="Exchange credentials")
def login(payload: LoginRequest, db: DbSession) -> TokenPair:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))

    if user is None or not verify_password(payload.password, user.password_hash):
        logger.warning("login_failed", email=payload.email)
        raise _REJECTED

    if not user.is_active:
        logger.warning("login_failed", email=payload.email, reason="inactive")
        raise _REJECTED

    user.last_login_at = datetime.now(UTC)
    db.commit()

    logger.info("login", user_id=str(user.id), role=user.role.value)
    return _issue(user)


@router.post("/auth/refresh", response_model=TokenPair, summary="Renew an access token")
def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    """Exchange a refresh token for a new pair.

    The account is re-read rather than trusted from the token: a refresh token
    lives for days, and an account disabled in the meantime must not be able to
    renew its way back in.
    """
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired refresh token",
        ) from exc

    try:
        user = db.get(User, uuid.UUID(str(claims["sub"])))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token subject"
        ) from exc

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="account is unavailable"
        )
    return _issue(user)


@router.get("/auth/me", response_model=Identity, summary="The current account")
def me(user: CurrentUser) -> Identity:
    return Identity(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        is_active=user.is_active,
    )
