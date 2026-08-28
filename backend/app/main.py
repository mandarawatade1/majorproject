"""FastAPI application factory and entrypoint.

Run locally:   uvicorn app.main:app --reload
In Docker:     handled by the image CMD
"""

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import health
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown.

    Startup deliberately does NOT block on dependencies being reachable: the
    container should come up and report itself unhealthy via /health/ready
    rather than crash-looping while Postgres is still starting.
    """
    logger.info(
        "startup",
        app=settings.app_name,
        env=settings.app_env,
        database=f"{settings.postgres_host}:{settings.postgres_port}",
        chroma=settings.chroma_url,
        ollama=settings.ollama_base_url,
    )
    yield
    logger.info("shutdown")


app = FastAPI(
    title=settings.app_name,
    description=(
        "AI-Based Institute Knowledge Management using Open-Source LLM and RAG Framework. "
        "B.Tech Computer Engineering major project, Pillai College of Engineering."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Bind a request_id to the log context and time every request.

    The same request_id will later be attached to each RAG pipeline stage, so a
    single question can be traced from HTTP entry through retrieval, reranking,
    agent iterations and verification.
    """
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled_exception", path=request.url.path, method=request.method)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-ms"] = str(elapsed_ms)

    if request.url.path not in ("/health", "/health/ready"):
        logger.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            elapsed_ms=elapsed_ms,
        )
    return response


# Health lives at the root, outside the versioned prefix, so orchestrators and
# the verify script never have to know the API version.
app.include_router(health.router)


@app.get("/", tags=["meta"], summary="Service banner")
async def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "version": "0.1.0",
        "phase": "0 — Foundations",
        "docs": "/docs",
        "health": "/health",
        "readiness": "/health/ready",
    }
