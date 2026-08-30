# ===========================================================================
# PCE KMS — common tasks.  Run `make` or `make help` for the list.
# ===========================================================================
.DEFAULT_GOAL := help
SHELL := /bin/bash

.PHONY: help bootstrap up down restart logs ps verify migrate revision \
        shell-api shell-db test lint format typecheck check pull-models \
        ingest crawl parse corpus-stats seed seed-corpus db-stats \
        rag-doctor rag-configs rag-index ask clean clean-all

help:  ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

bootstrap:  ## First-time setup: .env, LFS, stack up, migrations, verify
	./scripts/bootstrap.sh

up:  ## Start the stack in the background
	docker compose up -d --build

down:  ## Stop the stack (volumes preserved)
	docker compose down

restart:  ## Restart every service
	docker compose restart

logs:  ## Tail logs (make logs S=api to follow one service)
	docker compose logs -f $(S)

ps:  ## Show container status
	docker compose ps

verify:  ## Run the Phase 0 acceptance check
	./scripts/verify-stack.sh

migrate:  ## Apply migrations
	docker compose exec api alembic upgrade head

revision:  ## Autogenerate a migration: make revision M="add documents table"
	docker compose exec api alembic revision --autogenerate -m "$(M)"

shell-api:  ## Shell inside the api container
	docker compose exec api bash

shell-db:  ## psql inside the postgres container
	docker compose exec postgres psql -U $${POSTGRES_USER:-pce} -d $${POSTGRES_DB:-pce_kms}

test:  ## Run the test suite (backend + rag)
	pytest

lint:  ## ruff check
	cd backend && ruff check .
	ruff check rag

format:  ## ruff format
	cd backend && ruff format .
	ruff format rag

typecheck:  ## mypy
	cd backend && mypy app

check: lint typecheck test  ## Everything CI runs

pull-models:  ## Pull the Ollama models (~9.6 GB)
	docker compose up ollama-init

seed:  ## Seed the database: reference data, corpus, admin account
	docker compose exec api python -m app.seed

seed-corpus:  ## Load only the Phase 1 corpus into PostgreSQL
	docker compose exec api python -m app.seed corpus

db-stats:  ## Print what is actually in the database
	docker compose exec api python -m app.seed --help >/dev/null && \
	docker compose exec api python -c "from app.seed.__main__ import verify; from app.db.session import SessionLocal; \
	session=SessionLocal(); raise SystemExit(verify(session))"

ingest:  ## Full corpus ingestion: crawl -> parse -> manifest -> stats
	docker compose exec api python -m rag.ingestion all

crawl:  ## Fetch pages and PDFs into corpus/raw/
	docker compose exec api python -m rag.ingestion crawl

parse:  ## Parse raw + demo into corpus/normalised/
	docker compose exec api python -m rag.ingestion parse

corpus-stats:  ## Print corpus statistics and the real/demo ratio
	docker compose exec api python -m rag.ingestion stats

rag-doctor:  ## Check corpus, embedder, index and generator are reachable
	docker compose exec api python -m rag doctor

rag-configs:  ## List configurations C0-C5 and what each enables
	docker compose exec api python -m rag configs

rag-index:  ## Chunk, embed and index the corpus (make rag-index C=C0)
	docker compose exec api python -m rag index --config $(or $(C),C0)

ask:  ## Ask one question (make ask Q="What is the intake?")
	docker compose exec api python -m rag ask "$(Q)" --config $(or $(C),C0)

clean:  ## Remove Python caches
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -prune -exec rm -rf {} + 2>/dev/null || true

clean-all: down  ## DESTRUCTIVE: also delete volumes (database, vectors, models)
	@read -p "Delete all volumes including pulled models? [y/N] " a; \
	 [ "$$a" = "y" ] && docker compose down -v || echo "cancelled"
