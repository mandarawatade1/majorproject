"""Shared test fixtures.

Phase 0 tests are unit tests: they exercise the app without a database, so
`pytest` passes on a clean checkout with nothing running. Tests that need live
services must be marked @pytest.mark.integration and are excluded from the
default run.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
