# ===========================================================================
# Backend image — multi-stage so development (hot reload, dev deps) and
# production (lean, non-root) share one Dockerfile.
# ===========================================================================
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# libpq5 for psycopg; curl for humans debugging inside the container
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 curl \
 && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
FROM base AS development

COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---------------------------------------------------------------------------
FROM base AS production

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
