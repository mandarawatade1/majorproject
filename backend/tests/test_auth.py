"""Phase 6b: authentication and the admin gate.

Split deliberately. `TestTokens` and `TestPasswords` need neither a database nor
FastAPI, because the rules they cover — what expires, what is refused, what a
wrong password does — are the ones worth pinning precisely. The route tests
override the database dependency with a stub rather than standing up
PostgreSQL, so the whole file runs in CI without services.

Two behaviours here would be silent if broken, and both get their own test: a
refresh token accepted as an access token, and a placeholder signing key
accepted in production.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import jwt
import pytest
from app.core.config import settings
from app.models.enums import UserRole
from fastapi.testclient import TestClient

from app.api import deps
from app.core.security import (
    INSECURE_DEFAULT_KEY,
    INSECURE_EXAMPLE_KEY,
    InsecureConfigurationError,
    create_token,
    decode_token,
    hash_password,
    insecure_key_reason,
    verify_password,
)
from app.main import app


class _FakeUser:
    """Enough of `User` for the dependency chain."""

    def __init__(self, role: UserRole = UserRole.ADMIN, active: bool = True) -> None:
        self.id = uuid.uuid4()
        self.email = "admin@pce.local"
        self.full_name = "Administrator"
        self.role = role
        self.is_active = active
        self.password_hash = hash_password("correct-horse")
        self.last_login_at = None


class _FakeSession:
    """A stand-in for the SQLAlchemy session, returning one known user."""

    def __init__(self, user: _FakeUser | None) -> None:
        self.user = user

    def get(self, _model, ident):  # noqa: ANN001
        if self.user is None or str(self.user.id) != str(ident):
            return None
        return self.user

    def scalar(self, _statement):  # noqa: ANN001
        return self.user

    def commit(self) -> None:
        pass

    def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _no_leaked_overrides() -> Iterator[None]:
    """Clear dependency overrides after every test in this file.

    Autouse rather than tied to the `client` fixture, because several tests
    install a *second* database stub mid-test. If cleanup depended on
    requesting `client`, forgetting it would leave a stubbed database in place
    for whatever ran next — a failure that appears in an unrelated test.
    """
    yield
    app.dependency_overrides.clear()


def _client_for(user: _FakeUser | None) -> TestClient:
    """A client whose database contains exactly this user, or nobody."""
    app.dependency_overrides[deps.get_db] = lambda: _FakeSession(user)
    return TestClient(app)


@pytest.fixture
def user() -> _FakeUser:
    return _FakeUser()


@pytest.fixture
def client(user: _FakeUser) -> TestClient:
    return _client_for(user)


# ---------------------------------------------------------------------------


class TestPasswords:
    def test_a_hash_verifies_its_own_password(self) -> None:
        digest = hash_password("correct-horse")
        assert digest != "correct-horse"
        assert verify_password("correct-horse", digest)

    def test_a_wrong_password_does_not_verify(self) -> None:
        assert not verify_password("wrong", hash_password("correct-horse"))

    @pytest.mark.parametrize(
        ("password", "digest"),
        [("", "x"), ("pw", ""), ("pw", "not-a-bcrypt-hash")],
    )
    def test_malformed_input_is_false_not_an_exception(self, password: str, digest: str) -> None:
        """A corrupt hash should fail the login, not the request. Raising here
        would turn one bad row into a 500 that distinguishes it from a wrong
        password."""
        assert verify_password(password, digest) is False

    def test_the_same_password_hashes_differently_each_time(self) -> None:
        """bcrypt salts. Equal digests would mean the salt was lost."""
        assert hash_password("same") != hash_password("same")


class TestTokens:
    def test_a_token_round_trips_with_its_claims(self, user: _FakeUser) -> None:
        claims = decode_token(create_token(user.id, "admin"))
        assert claims["sub"] == str(user.id)
        assert claims["role"] == "admin"
        assert claims["type"] == "access"
        assert claims["jti"]

    def test_a_refresh_token_is_not_an_access_token(self, user: _FakeUser) -> None:
        """The check that stops a stolen refresh token granting days of API
        access instead of one exchange at the refresh endpoint."""
        refresh = create_token(user.id, "admin", "refresh")
        with pytest.raises(jwt.InvalidTokenError):
            decode_token(refresh, expected_type="access")
        assert decode_token(refresh, expected_type="refresh")["type"] == "refresh"

    def test_an_expired_token_is_rejected(self, user: _FakeUser) -> None:
        expired = create_token(user.id, "admin", "access", expires_delta=timedelta(seconds=-1))
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_token(expired)

    def test_a_token_signed_with_another_key_is_rejected(
        self, user: _FakeUser, monkeypatch
    ) -> None:
        token = create_token(user.id, "admin")
        monkeypatch.setattr(settings, "secret_key", "a-different-key-entirely")
        with pytest.raises(jwt.InvalidSignatureError):
            decode_token(token)

    def test_a_tampered_role_breaks_the_signature(self, user: _FakeUser) -> None:
        """Privilege escalation by editing the payload must not work."""
        forged = jwt.encode(
            {"sub": str(user.id), "role": "admin", "type": "access"},
            "not-the-real-key",
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(jwt.InvalidTokenError):
            decode_token(forged)


_REAL_KEY = "6f3a1c0d8b47e29f5a1d3c7b0e964812fa5d7c3b1e0a9482"


class TestThePlaceholderKeyIsRefusedInProduction:
    """The silent total bypass this guard exists to prevent.

    There are two published placeholders, not one: `config.py` declares a
    default, and `.env.example` overrides it with a different string. Copying
    `.env.example` to `.env` — the documented first step — therefore produces a
    key the field default never sees. A guard that knew only the field default
    would let exactly the realistic case through while appearing to cover it.
    """

    @pytest.mark.parametrize("key", [INSECURE_DEFAULT_KEY, INSECURE_EXAMPLE_KEY])
    def test_production_refuses_to_sign_with_a_published_key(self, key: str, monkeypatch) -> None:
        monkeypatch.setattr(settings, "secret_key", key)
        monkeypatch.setattr(settings, "app_env", "production")
        with pytest.raises(InsecureConfigurationError):
            create_token(uuid.uuid4(), "admin")

    def test_the_key_env_example_actually_ships_is_one_of_them(self) -> None:
        """Read the file rather than trusting the constant.

        This is the test that fails if someone edits `.env.example` and leaves
        the guard behind — the drift that made the guard useless in the first
        place. Skipped where the file is not shipped, as in the API image.
        """
        example = Path(__file__).resolve().parents[2] / ".env.example"
        if not example.exists():
            pytest.skip("no .env.example in this tree")
        shipped = [
            line.split("=", 1)[1].split("#")[0].strip()
            for line in example.read_text().splitlines()
            if line.startswith("SECRET_KEY=")
        ]
        assert shipped, "SECRET_KEY vanished from .env.example"
        for key in shipped:
            assert insecure_key_reason(key) is not None, (
                f"{key!r} ships in .env.example but the guard would accept it"
            )

    def test_a_short_key_is_refused_in_production(self, monkeypatch) -> None:
        """A key someone typed by hand is not a key."""
        monkeypatch.setattr(settings, "secret_key", "hunter2")
        monkeypatch.setattr(settings, "app_env", "production")
        with pytest.raises(InsecureConfigurationError):
            create_token(uuid.uuid4(), "admin")

    def test_development_with_the_default_key_warns_but_works(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "secret_key", INSECURE_DEFAULT_KEY)
        monkeypatch.setattr(settings, "app_env", "development")
        assert create_token(uuid.uuid4(), "admin")

    def test_production_with_a_real_key_is_fine(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "secret_key", _REAL_KEY)
        monkeypatch.setattr(settings, "app_env", "production")
        assert create_token(uuid.uuid4(), "admin")


class TestLogin:
    def test_correct_credentials_return_a_token_pair(self, client: TestClient) -> None:
        response = client.post(
            f"{settings.api_prefix}/auth/login",
            json={"email": "admin@pce.local", "password": "correct-horse"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert decode_token(body["access_token"])["role"] == "admin"
        assert decode_token(body["refresh_token"], "refresh")

    def test_a_wrong_password_is_rejected(self, client: TestClient) -> None:
        response = client.post(
            f"{settings.api_prefix}/auth/login",
            json={"email": "admin@pce.local", "password": "wrong"},
        )
        assert response.status_code == 401

    def test_an_unknown_account_gives_the_same_message(self, client: TestClient) -> None:
        """No account-enumeration oracle: an attacker must not be able to learn
        which addresses exist by comparing responses."""
        wrong_password = client.post(
            f"{settings.api_prefix}/auth/login",
            json={"email": "admin@pce.local", "password": "wrong"},
        )
        unknown_account = _client_for(None).post(
            f"{settings.api_prefix}/auth/login",
            json={"email": "nobody@pce.local", "password": "wrong"},
        )
        assert wrong_password.status_code == unknown_account.status_code == 401
        assert wrong_password.json() == unknown_account.json()

    def test_an_inactive_account_cannot_log_in(self) -> None:
        response = _client_for(_FakeUser(active=False)).post(
            f"{settings.api_prefix}/auth/login",
            json={"email": "admin@pce.local", "password": "correct-horse"},
        )
        assert response.status_code == 401


class TestTheAdminGate:
    def _headers(self, user: _FakeUser) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_token(user.id, user.role.value)}"}

    def test_an_admin_reaches_an_admin_route(self, client: TestClient, user: _FakeUser) -> None:
        response = client.get(
            f"{settings.api_prefix}/admin/index/status", headers=self._headers(user)
        )
        assert response.status_code == 200
        assert "running" in response.json()

    def test_no_credentials_is_401(self, client: TestClient) -> None:
        response = client.get(f"{settings.api_prefix}/admin/index/status")
        assert response.status_code == 401

    def test_a_non_admin_account_is_403_not_401(self) -> None:
        """The distinction matters: 401 means "who are you", 403 means "I know
        who you are and the answer is no". Conflating them tells a signed-in
        user to log in again, which they cannot fix."""
        viewer = _FakeUser(role=UserRole.STUDENT)
        response = _client_for(viewer).get(
            f"{settings.api_prefix}/admin/index/status",
            headers=self._headers(viewer),
        )
        assert response.status_code == 403

    def test_a_token_for_a_deleted_account_is_rejected(self, user: _FakeUser) -> None:
        """The database is the authority on whether an account still exists.

        The role travels in the token so ordinary checks need no query, but a
        token issued before an account was removed must stop working, and a
        signed blob cannot know that.
        """
        response = _client_for(None).get(
            f"{settings.api_prefix}/admin/index/status", headers=self._headers(user)
        )
        assert response.status_code == 401

    def test_a_refresh_token_does_not_open_an_admin_route(
        self, client: TestClient, user: _FakeUser
    ) -> None:
        refresh = create_token(user.id, "admin", "refresh")
        response = client.get(
            f"{settings.api_prefix}/admin/index/status",
            headers={"Authorization": f"Bearer {refresh}"},
        )
        assert response.status_code == 401


class TestThePublicSurfaceStaysPublic:
    """Adding auth must not have quietly closed the portal.

    The whole point of the deployment is that a prospective student browses and
    asks questions without an account.
    """

    def test_the_chat_config_list_needs_no_credentials(self, client: TestClient) -> None:
        assert client.get(f"{settings.api_prefix}/chat/configs").status_code == 200

    def test_health_needs_no_credentials(self, client: TestClient) -> None:
        assert client.get("/health").status_code == 200


class TestRebuildIsGuarded:
    def _admin_headers(self, user: _FakeUser) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_token(user.id, 'admin')}"}

    def test_the_confirmation_string_is_required(self, client: TestClient, user: _FakeUser) -> None:
        """A rebuild destroys an index that takes minutes to restore. A typed
        confirmation is the difference between a decision and a misclick."""
        response = client.post(
            f"{settings.api_prefix}/admin/index/rebuild",
            json={"config": "C3", "confirm": "yes"},
            headers=self._admin_headers(user),
        )
        assert response.status_code == 400
        assert "REBUILD" in response.json()["detail"]

    def test_an_anonymous_caller_cannot_start_one(self, client: TestClient) -> None:
        response = client.post(
            f"{settings.api_prefix}/admin/index/rebuild",
            json={"config": "C3", "confirm": "REBUILD"},
        )
        assert response.status_code == 401
