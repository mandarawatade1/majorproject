"""Health and readiness endpoints.

/health        liveness  — is this process up? No dependencies touched.
/health/ready  readiness — are PostgreSQL, Redis, Chroma and Ollama all
                           reachable, and are the required models pulled?

/health/ready is the single command that answers "is the stack green?", and is
what scripts/verify-stack.sh calls. It returns 200 when everything is up and
503 when anything is not, so it works as a CI gate too.
"""

import asyncio
import time
from typing import Any

import httpx
import redis
from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import check_database

logger = get_logger(__name__)
router = APIRouter(tags=["health"])

PROBE_TIMEOUT_SECONDS = 5.0


def _ok(detail: str, **extra: Any) -> dict[str, Any]:
    return {"status": "up", "detail": detail, **extra}


def _fail(detail: str, **extra: Any) -> dict[str, Any]:
    return {"status": "down", "detail": detail, **extra}


async def _check_postgres() -> dict[str, Any]:
    reachable = await asyncio.to_thread(check_database)
    host = f"{settings.postgres_host}:{settings.postgres_port}"
    return _ok("SELECT 1 succeeded", host=host) if reachable else _fail("cannot connect", host=host)


async def _check_redis() -> dict[str, Any]:
    host = f"{settings.redis_host}:{settings.redis_port}"

    def _ping() -> bool:
        client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            socket_connect_timeout=PROBE_TIMEOUT_SECONDS,
        )
        try:
            return bool(client.ping())
        finally:
            client.close()

    try:
        alive = await asyncio.to_thread(_ping)
        return _ok("PONG", host=host) if alive else _fail("no PONG", host=host)
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}", host=host)


async def _check_chroma() -> dict[str, Any]:
    """Chroma moved its heartbeat from /api/v1 to /api/v2; accept either."""
    base = settings.chroma_url
    async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_SECONDS) as client:
        for version in ("v2", "v1"):
            try:
                response = await client.get(f"{base}/api/{version}/heartbeat")
                if response.status_code == 200:
                    return _ok(f"heartbeat via /api/{version}", host=base)
            except Exception:  # noqa: S110 - try the other API version
                continue
    return _fail("no heartbeat on /api/v2 or /api/v1", host=base)


async def _check_ollama() -> dict[str, Any]:
    """Up is not enough — report whether the two required models are pulled."""
    base = settings.ollama_base_url
    required = [settings.ollama_generator_model, settings.ollama_judge_model]

    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{base}/api/tags")
            response.raise_for_status()
            available = [m.get("name", "") for m in response.json().get("models", [])]
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}", host=base, required_models=required)

    missing = [m for m in required if m not in available]
    if missing:
        return _fail(
            "server up, required models not pulled",
            host=base,
            available_models=available,
            missing_models=missing,
            hint="docker compose up ollama-init   (or: ollama pull " + missing[0] + ")",
        )
    return _ok("server up, all required models present", host=base, available_models=available)


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, Any]:
    """Is the API process alive? Deliberately touches no dependency."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
        "version": "0.1.0",
    }


@router.get("/health/ready", summary="Readiness probe across all dependencies")
async def readiness(response: Response) -> dict[str, Any]:
    """Probe every dependency in parallel and report a per-service verdict."""
    started = time.perf_counter()

    names = ("postgres", "redis", "chroma", "ollama")
    results = await asyncio.gather(
        _check_postgres(),
        _check_redis(),
        _check_chroma(),
        _check_ollama(),
        return_exceptions=True,
    )

    checks: dict[str, Any] = {}
    for name, result in zip(names, results, strict=True):
        if isinstance(result, BaseException):
            checks[name] = _fail(f"probe raised {type(result).__name__}: {result}")
        else:
            checks[name] = result

    all_up = all(c["status"] == "up" for c in checks.values())
    if not all_up:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        logger.warning(
            "readiness_failed",
            down=[n for n, c in checks.items() if c["status"] != "up"],
        )

    return {
        "status": "ready" if all_up else "not_ready",
        "checks": checks,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
    }
