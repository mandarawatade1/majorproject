#!/usr/bin/env bash
# ===========================================================================
# Phase 0 acceptance check.
#
#   ./scripts/verify-stack.sh
#
# Confirms that PostgreSQL, Redis, Chroma and Ollama are up, that the required
# models are pulled, and that Alembic can reach the database. Exits non-zero if
# anything is red, so it doubles as a CI/pre-demo gate.
# ===========================================================================
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'; DIM=$'\033[2m'; RESET=$'\033[0m'
PASS=0; FAIL=0

ok()   { printf '  %sPASS%s  %s\n' "$GREEN" "$RESET" "$1"; PASS=$((PASS+1)); }
bad()  { printf '  %sFAIL%s  %s\n' "$RED" "$RESET" "$1"; [ $# -gt 1 ] && printf '        %s%s%s\n' "$DIM" "$2" "$RESET"; FAIL=$((FAIL+1)); }
warn() { printf '  %sWARN%s  %s\n' "$YELLOW" "$RESET" "$1"; }
head_() { printf '\n%s\n' "$1"; }

[ -f .env ] && set -a && . ./.env && set +a

API_PORT="${API_PORT:-8000}"
CHROMA_HOST_PORT="${CHROMA_HOST_PORT:-8001}"
OLLAMA_HOST_PORT="${OLLAMA_HOST_PORT:-11434}"
POSTGRES_HOST_PORT="${POSTGRES_HOST_PORT:-5432}"
REDIS_HOST_PORT="${REDIS_HOST_PORT:-6379}"
GEN_MODEL="${OLLAMA_GENERATOR_MODEL:-qwen2.5:7b-instruct-q4_K_M}"
JUDGE_MODEL="${OLLAMA_JUDGE_MODEL:-llama3.1:8b-instruct-q4_K_M}"

printf '%s\n' "PCE KMS — Phase 0 stack verification"
printf '%s\n' "===================================="

# --- Prerequisites ---------------------------------------------------------
head_ "Prerequisites"
if command -v docker >/dev/null 2>&1; then ok "docker CLI: $(docker --version | cut -d, -f1)"
else bad "docker CLI not found" "Install Docker Desktop, then re-run."; fi

if docker info >/dev/null 2>&1; then
  ok "docker daemon reachable"
  MEM_BYTES=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
  MEM_GB=$(( MEM_BYTES / 1024 / 1024 / 1024 ))
  if [ "$MEM_GB" -ge 12 ]; then ok "docker memory limit: ${MEM_GB} GB"
  elif [ "$MEM_GB" -gt 0 ]; then
    warn "docker memory limit is ${MEM_GB} GB — a 7B model needs ~12 GB."
    printf '        %sDocker Desktop -> Settings -> Resources -> Memory%s\n' "$DIM" "$RESET"
  fi
else
  bad "docker daemon not running" "Start Docker Desktop and re-run."
fi

[ -f .env ] && ok ".env present" || bad ".env missing" "cp .env.example .env"

if [ -f .env ] && grep -q 'SECRET_KEY=CHANGE_ME' .env 2>/dev/null; then
  warn "SECRET_KEY is still the placeholder"
  printf '        %spython -c "import secrets; print(secrets.token_urlsafe(48))"%s\n' "$DIM" "$RESET"
fi

# --- Containers ------------------------------------------------------------
head_ "Containers"
for svc in postgres redis chroma ollama; do
  state=$(docker compose ps --format '{{.Service}} {{.State}}' 2>/dev/null | awk -v s="$svc" '$1==s {print $2}')
  case "$state" in
    running) ok "$svc container running" ;;
    "")      bad "$svc container not created" "docker compose up -d $svc" ;;
    *)       bad "$svc container state: $state" ;;
  esac
done

# --- Service health --------------------------------------------------------
head_ "Service health"

if docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-pce}" -d "${POSTGRES_DB:-pce_kms}" >/dev/null 2>&1; then
  ok "postgres accepting connections (:$POSTGRES_HOST_PORT)"
else
  bad "postgres not ready" "docker compose logs postgres"
fi

if [ "$(docker compose exec -T redis redis-cli ping 2>/dev/null | tr -d '\r')" = "PONG" ]; then
  ok "redis responding to PING (:$REDIS_HOST_PORT)"
else
  bad "redis not responding" "docker compose logs redis"
fi

CHROMA_OK=""
for v in v2 v1; do
  if curl -fsS --max-time 5 "http://localhost:${CHROMA_HOST_PORT}/api/${v}/heartbeat" >/dev/null 2>&1; then
    CHROMA_OK="$v"; break
  fi
done
if [ -n "$CHROMA_OK" ]; then ok "chroma heartbeat via /api/${CHROMA_OK} (:$CHROMA_HOST_PORT)"
else bad "chroma heartbeat failed" "docker compose logs chroma"; fi

TAGS=$(curl -fsS --max-time 5 "http://localhost:${OLLAMA_HOST_PORT}/api/tags" 2>/dev/null)
if [ -n "$TAGS" ]; then
  ok "ollama API responding (:$OLLAMA_HOST_PORT)"
  for m in "$GEN_MODEL" "$JUDGE_MODEL"; do
    if printf '%s' "$TAGS" | grep -q "\"$m\""; then
      ok "model pulled: $m"
    else
      bad "model missing: $m" "docker compose up ollama-init   (~5 GB per model)"
    fi
  done
else
  bad "ollama API not responding" "docker compose logs ollama"
fi

# --- Application -----------------------------------------------------------
head_ "Application"

if curl -fsS --max-time 5 "http://localhost:${API_PORT}/health" >/dev/null 2>&1; then
  ok "api liveness /health (:$API_PORT)"
else
  bad "api /health unreachable" "docker compose logs api"
fi

READY=$(curl -sS --max-time 30 "http://localhost:${API_PORT}/health/ready" 2>/dev/null)
if printf '%s' "$READY" | grep -q '"status": *"ready"'; then
  ok "api readiness: all four dependencies up"
elif [ -n "$READY" ]; then
  bad "api readiness reports not_ready"
  printf '%s%s%s\n' "$DIM" "$(printf '%s' "$READY" | head -c 700)" "$RESET"
else
  bad "api readiness unreachable"
fi

if docker compose exec -T api alembic current 2>/dev/null | grep -q .; then
  ok "alembic reachable; current revision: $(docker compose exec -T api alembic current 2>/dev/null | tail -1 | tr -d '\r')"
else
  bad "alembic could not read the database" "docker compose exec api alembic upgrade head"
fi

# --- Summary ---------------------------------------------------------------
printf '\n====================================\n'
if [ "$FAIL" -eq 0 ]; then
  printf '%sAll %d checks passed. Phase 0 stack is green.%s\n\n' "$GREEN" "$PASS" "$RESET"
  exit 0
fi
printf '%s%d passed, %d failed.%s\n\n' "$RED" "$PASS" "$FAIL" "$RESET"
exit 1
