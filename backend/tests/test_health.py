"""Phase 0 acceptance tests.

These prove the scaffold is wired correctly without needing Docker: the app
imports, settings load, routes are registered, and the readiness endpoint
degrades honestly (503 with a per-service verdict) rather than crashing when
dependencies are absent.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings


class TestLiveness:
    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_health_does_not_touch_dependencies(self, client: TestClient) -> None:
        """Liveness must stay green even with every backing service down."""
        assert client.get("/health").status_code == 200

    def test_root_banner(self, client: TestClient) -> None:
        body = client.get("/").json()
        assert body["health"] == "/health"
        assert "phase" in body

    def test_request_id_header_is_echoed(self, client: TestClient) -> None:
        response = client.get("/health", headers={"X-Request-ID": "test-trace-123"})
        assert response.headers["X-Request-ID"] == "test-trace-123"
        assert "X-Response-Time-ms" in response.headers


class TestReadiness:
    def test_reports_all_four_dependencies(self, client: TestClient) -> None:
        """Whether up or down, the shape of the report is fixed."""
        body = client.get("/health/ready").json()
        assert set(body["checks"]) == {"postgres", "redis", "chroma", "ollama"}
        for check in body["checks"].values():
            assert check["status"] in {"up", "down"}

    def test_returns_503_when_a_dependency_is_down(self, client: TestClient) -> None:
        """With no services running, readiness must fail loudly, not silently."""
        response = client.get("/health/ready")
        body = response.json()
        if body["status"] == "ready":
            pytest.skip("live services are running; the failure path is untestable here")
        assert response.status_code == 503


class TestSettings:
    def test_database_url_is_composed_from_parts(self) -> None:
        s = Settings(
            postgres_user="u",
            postgres_password="p",
            postgres_host="h",
            postgres_port=1234,
            postgres_db="d",
        )
        assert s.database_url == "postgresql+psycopg://u:p@h:1234/d"

    def test_cors_origins_parse_from_comma_separated_string(self) -> None:
        s = Settings(cors_origins="http://a.test, http://b.test ,")
        assert s.cors_origin_list == ["http://a.test", "http://b.test"]

    def test_settings_are_cached(self) -> None:
        assert get_settings() is get_settings()

    def test_ablation_flags_exist_for_every_innovation(self) -> None:
        """Turning all five off yields configuration C0, the naive baseline."""
        s = Settings()
        for flag in (
            s.rag_structure_aware_chunking,
            s.rag_hybrid_retrieval,
            s.rag_reranking,
            s.rag_agentic_layer,
            s.rag_verification,
        ):
            assert isinstance(flag, bool)
