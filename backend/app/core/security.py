"""Password hashing and JSON Web Tokens.

Kept free of FastAPI and of the database so the rules can be tested directly:
what makes a token valid, what makes it expire, and what refuses to issue one
at all.

That last point is the reason this module has an opinion. `settings.secret_key`
ships with a placeholder value, and a placeholder signing key means anyone who
has read the repository can mint an administrator token. In development that is
a convenience; in production it is a total authentication bypass, and it is
silent — everything works, which is exactly why nobody notices. So issuing a
token with the default key is refused outright when the environment is
production, and logged as a warning otherwise.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from app.core.config import settings
from app.core.logging import get_logger
from passlib.context import CryptContext

logger = get_logger(__name__)

# bcrypt, matching what `app/seed/__main__.py` used to hash the admin password.
# Changing the scheme here without a migration would lock that account out.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Every signing key an attacker can read without breaking in. There are two,
# and checking only one is worse than checking neither, because it looks like
# the problem is handled: `config.py` supplies the first as a field default,
# but `.env.example` overrides it with the second, and copying `.env.example`
# to `.env` is exactly how a real deployment ends up with a published key.
INSECURE_DEFAULT_KEY = "dev-only-insecure-key-change-me"
INSECURE_EXAMPLE_KEY = "CHANGE_ME_generate_a_long_random_string_before_first_run"
_PUBLISHED_KEYS = frozenset({INSECURE_DEFAULT_KEY, INSECURE_EXAMPLE_KEY})

# HS256 signatures are only as strong as the shared secret. Anything short
# enough to be guessed offline is not a key, whatever it was meant to be.
_MIN_KEY_LENGTH = 32

TokenType = Literal["access", "refresh"]


class InsecureConfigurationError(RuntimeError):
    """Raised rather than issuing a token signed with a published key."""


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Check a password against its hash.

    A malformed or empty hash returns False rather than raising: a corrupt row
    should fail the login, not the request, and certainly not with a stack
    trace that distinguishes it from a wrong password.
    """
    if not password or not password_hash:
        return False
    try:
        return _pwd_context.verify(password, password_hash)
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


def insecure_key_reason(key: str) -> str | None:
    """Why this signing key must not be trusted, or None if it is fine.

    Separated from the check so it can be tested against the literal strings
    the repository actually ships, which is the only way to know the guard
    fires. A guard that names one placeholder while the deployment uses a
    different one is worse than no guard: it reports the problem as handled.
    """
    if not key:
        return "it is empty"
    if key in _PUBLISHED_KEYS:
        return "it is a placeholder published in this repository"
    if key.upper().startswith("CHANGE_ME"):
        return "it still begins with CHANGE_ME"
    if len(key) < _MIN_KEY_LENGTH:
        return f"it is only {len(key)} characters; use at least {_MIN_KEY_LENGTH}"
    return None


def _check_signing_key() -> None:
    reason = insecure_key_reason(settings.secret_key)
    if reason is None:
        return
    if settings.app_env == "production":
        raise InsecureConfigurationError(
            f"SECRET_KEY cannot be used to sign tokens because {reason}. Anyone "
            "who can guess or read it could mint an administrator token. Set "
            "SECRET_KEY to a long random value before running in production."
        )
    logger.warning("insecure_secret_key", detail=f"SECRET_KEY is unsafe: {reason}")


def create_token(
    subject: str | uuid.UUID,
    role: str,
    token_type: TokenType = "access",
    expires_delta: timedelta | None = None,
) -> str:
    """Sign a token for one user.

    `role` is embedded so an authorisation check needs no database round trip.
    The trade-off is deliberate and worth naming: a role changed in the
    database does not take effect until the token expires. Access tokens are
    short-lived (30 minutes by default) precisely to bound that window.
    """
    _check_signing_key()

    now = datetime.now(UTC)
    if expires_delta is None:
        expires_delta = (
            timedelta(minutes=settings.access_token_expire_minutes)
            if token_type == "access"
            else timedelta(days=settings.refresh_token_expire_days)
        )

    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        # A unique id per token, so a future revocation list has something to
        # key on without changing the token shape.
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: TokenType = "access") -> dict[str, Any]:
    """Decode and validate a token, or raise `jwt.InvalidTokenError`.

    The type check is not ceremony. A refresh token lives for days; if it were
    accepted as an access token, a stolen refresh token would grant days of API
    access rather than one exchange at the refresh endpoint.
    """
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(
            f"expected a {expected_type} token, got {payload.get('type')!r}"
        )
    if not payload.get("sub"):
        raise jwt.InvalidTokenError("token carries no subject")
    return payload


__all__ = [
    "INSECURE_DEFAULT_KEY",
    "INSECURE_EXAMPLE_KEY",
    "InsecureConfigurationError",
    "create_token",
    "decode_token",
    "hash_password",
    "insecure_key_reason",
    "verify_password",
]
