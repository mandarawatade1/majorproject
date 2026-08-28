#!/usr/bin/env bash
# ===========================================================================
# One-command first-time setup.
#
#   ./scripts/bootstrap.sh
#
# Creates .env (with a real SECRET_KEY), installs Git LFS hooks, brings the
# stack up, applies migrations, then runs the verification script.
# ===========================================================================
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Checking prerequisites"
command -v docker >/dev/null || { echo "Docker is required. Install Docker Desktop."; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker daemon is not running. Start Docker Desktop."; exit 1; }

echo "==> Git LFS"
if command -v git-lfs >/dev/null 2>&1; then
  git lfs install --local
  echo "    LFS hooks installed. Tracked patterns are in .gitattributes."
else
  echo "    git-lfs NOT installed. Install it before committing Docs/*.docx or *.pdf:"
  echo "      macOS:  brew install git-lfs"
  echo "      Ubuntu: sudo apt-get install git-lfs"
fi

echo "==> .env"
if [ -f .env ]; then
  echo "    .env already exists, leaving it alone."
else
  cp .env.example .env
  KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
  if [[ "$OSTYPE" == darwin* ]]; then
    sed -i '' "s|^SECRET_KEY=.*|SECRET_KEY=${KEY}|" .env
  else
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${KEY}|" .env
  fi
  echo "    Created .env with a freshly generated SECRET_KEY."
  echo "    Review ADMIN_PASSWORD and POSTGRES_PASSWORD before any non-local use."
fi

echo "==> Starting the stack (first run downloads ~9.6 GB of models)"
docker compose up -d --build

echo "==> Waiting for PostgreSQL"
for _ in $(seq 1 60); do
  docker compose exec -T postgres pg_isready -q && break
  sleep 2
done

echo "==> Applying database migrations"
docker compose exec -T api alembic upgrade head

echo "==> Verifying"
./scripts/verify-stack.sh
