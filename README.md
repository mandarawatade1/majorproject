# AI-Based Institute Knowledge Management using Open-Source LLM and RAG Framework

A secure, fully on-premise knowledge management system for an academic
institution. Institutional documents are ingested, chunked with their structure
preserved, indexed for hybrid semantic and keyword search, and answered by an
open-source LLM that must cite its sources and have every claim verified
against them.

**No proprietary AI is used anywhere in this system, including evaluation.**
Nothing leaves the machine it runs on.

> B.Tech Computer Engineering major project · Pillai College of Engineering,
> New Panvel · University of Mumbai · AY 2025-26
> Bhavesh Patil (B542) · Arpit Bolade (B509) · Soham Mali (B528) ·
> Mandar Awatade (B505) · Supervisor: Prof. Radhika Fulzele

---

## Status: Phase 0 — Foundations

| Phase | Description | Status |
|---|---|---|
| **0** | Foundations: scaffold, Docker stack, Alembic, CI | **complete** |
| **1** | Corpus acquisition: crawler, parsers, real/demo labelling | **complete** — 765 documents, 94.9% real |
| **2** | Data layer: full schema, migrations, seed | **complete** |
| **3** | Baseline RAG (**C0**) — the comparison baseline | **complete** — evaluated, 20 questions |
| **4** | Structure-aware chunking, hybrid retrieval, reranking (**C1-C3**) | **complete** — evaluated, plus C1-CONTROL |
| **5** | Agentic planner-executor and verification (**C4-C5**) | **complete** — evaluated |
| **6** | Backend API: auth, portal endpoints, streaming chat | **complete** — 6a portal + SSE, 6b auth + admin |
| **7** | Portal frontend (Next.js) | **complete** — home, departments, programmes, faculty |
| **8** | Ask PCE chat, knowledge explorer, baseline-vs-proposed comparison | **complete** — streaming chat with citations, /explore, /compare |
| 9 | Admin console | partial — endpoints exist, no UI |
| 10 | Evaluation: RAGAS, LLM-judge, ablation study | mostly done — 7 configs over 140 questions; RAGAS harness outstanding |
| 11 | Hardening and handover | not started |

Nine of twelve phases complete. The evaluation data is collected and
Chapter 4 is drafted; what remains in Phase 10 is the RAGAS harness, not the
ablation study.

The full design lives in **[`Docs/architecture-plan.md`](Docs/architecture-plan.md)**.
Read that before changing anything structural.

---

## What makes this more than a chatbot

Five things, each measurable in isolation via the ablation flags in `.env`:

1. **Structure-aware semantic chunking** — chunks respect document hierarchy
   and never cross a heading boundary; low-information boilerplate is filtered
   out; every chunk keeps its section path and page number.
2. **Hybrid retrieval** — dense vectors and BM25 in parallel, fused with
   Reciprocal Rank Fusion, then reordered by a cross-encoder reranker.
3. **Agentic reasoning** — a LangGraph planner decomposes multi-step
   questions, an executor retrieves per sub-question, and a critic decides
   whether to answer or retry with a rewritten query.
4. **Citation-backed generation** — every factual sentence carries a marker
   resolving to a document, section and page. No support, no answer.
5. **Post-answer verification** — the answer is split into atomic claims and
   each is entailment-checked against its own cited chunk before it is shown.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Docker Desktop | **Memory limit raised to at least 12 GB** — Settings → Resources. The default 8 GB is not enough for a 7B model. |
| ~25 GB free disk | Images, two LLMs (~9.6 GB), Postgres and vector data |
| 16 GB RAM | Confirmed available; drives the model choice below |
| Git LFS | `brew install git-lfs` — required before committing `Docs/*.docx` or `*.pdf` |
| Python 3.11+ | Only if running the backend outside Docker |

---

## Quickstart

```bash
git clone <repo-url> && cd majorproject2026
git lfs install
./scripts/bootstrap.sh
```

`bootstrap.sh` creates `.env` with a real `SECRET_KEY`, installs LFS hooks,
builds and starts the stack, applies migrations, and runs the verification
script.

Manually, if you prefer:

```bash
cp .env.example .env
# edit SECRET_KEY, ADMIN_PASSWORD, POSTGRES_PASSWORD
docker compose up -d --build
docker compose exec api alembic upgrade head
./scripts/verify-stack.sh
```

### First run downloads about 9.6 GB

`ollama-init` pulls the generator (`qwen2.5:7b-instruct-q4_K_M`, ~4.7 GB) and
the judge (`llama3.1:8b-instruct-q4_K_M`, ~4.9 GB). It runs in parallel with
the API and does not block startup, but `verify-stack.sh` will report the
models as missing until it finishes. Watch it with:

```bash
docker compose logs -f ollama-init
```

Set `OLLAMA_AUTO_PULL=false` in `.env` to skip it.

### Verifying the stack is green

```bash
./scripts/verify-stack.sh
```

Checks prerequisites, container states, PostgreSQL, Redis, Chroma, Ollama plus
both models, the API's own readiness endpoint, and Alembic. Exits non-zero if
anything is red, so it also works as a pre-demo gate.

The API reports the same thing itself:

```bash
curl -s localhost:8000/health/ready | python3 -m json.tool
```

| Endpoint | Purpose |
|---|---|
| http://localhost:8000/health | Liveness — touches no dependency |
| http://localhost:8000/health/ready | Readiness — probes all four services |
| http://localhost:8000/docs | Interactive API documentation |

---

## Ollama on macOS — read this before demo day

Docker cannot pass Apple's Metal GPU through to a container, so the
containerised Ollama in this compose file runs **CPU-only**. It works, but a 7B
model will feel slow.

For the demo, run Ollama natively instead:

```bash
brew install ollama
ollama serve
ollama pull qwen2.5:7b-instruct-q4_K_M
ollama pull llama3.1:8b-instruct-q4_K_M
```

Then in `.env`:

```
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

and start everything except the containerised Ollama:

```bash
docker compose up -d postgres redis chroma api
```

Metal acceleration typically makes generation several times faster. Worth
doing before any live demonstration.

---

## Project layout

```
majorproject2026/
├── Docs/
│   ├── architecture-plan.md      # the approved design — start here
│   ├── Report final (1).docx     # Git LFS
│   └── survey paper (1).pdf      # Git LFS
├── backend/                      # FastAPI application
│   ├── app/
│   │   ├── main.py               # app factory, middleware, request tracing
│   │   ├── core/                 # settings, structured logging
│   │   ├── db/                   # declarative base, engine, session
│   │   ├── models/               # ORM models (Phase 2)
│   │   └── api/routes/           # health now, the rest from Phase 6
│   ├── alembic/                  # migrations
│   ├── tests/
│   └── Dockerfile                # development + production stages
├── rag/                          # knowledge service (Phases 1, 3-5)
├── eval/                         # RAGAS harness + Streamlit console (Phase 10)
├── frontend/                     # Next.js portal (Phase 7)
├── corpus/
│   ├── raw/                      # as-fetched (gitignored)
│   ├── normalised/               # markdown + metadata (gitignored)
│   └── demo/                     # synthetic internal docs (tracked, labelled)
├── scripts/                      # bootstrap.sh, verify-stack.sh
├── docker-compose.yml
└── Makefile                      # make help
```

---

## Common tasks

```bash
make help            # list everything
make up / down       # start / stop the stack
make verify          # Phase 0 acceptance check
make logs S=api      # tail one service
make migrate         # alembic upgrade head
make revision M="add documents table"
make check           # lint + typecheck + test, exactly what CI runs
make pull-models     # fetch the Ollama models
```

---

## Real data vs demo data

Roughly **80%** of the corpus is real public information from
[pce.ac.in](https://www.pce.ac.in/) — institute profile, accreditation,
programmes and intakes, curricula, faculty, events, admissions, library,
research, annual reports.

Roughly **20%** is clearly labelled synthetic data standing in for internal
material no institution publishes: internal wikis, SOPs, circulars, lab
manuals, helpdesk articles. See [`corpus/demo/README.md`](corpus/demo/README.md).

`is_demo` is a database column, not a naming convention. It propagates from
document to chunk to citation, and the UI badges every demo-sourced citation.
Nothing synthetic is ever presented as institutional fact.

### Crawling policy

The Phase 1 crawler obeys `robots.txt`, identifies itself with a descriptive
User-Agent naming the project and a contact address, rate-limits to roughly one
request per second, stays within `pce.ac.in` and `admissions.pce.ac.in`, and
caches locally so the site is crawled once rather than on every run. Every
document retains its source URL and fetch timestamp. The corpus is for academic
evaluation and is not redistributed.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `port is already allocated` | Change `*_HOST_PORT` in `.env` |
| Ollama OOM or killed | Raise Docker's memory limit to 12 GB+, or use a 3B model |
| Chroma health check failing | `docker compose logs chroma`; the probe tries `/api/v2` then `/api/v1` |
| `alembic: command not found` | Run it inside the container: `docker compose exec api alembic ...` |
| Answers are very slow | Use native Ollama on macOS (see above) |
| Docs files committed as tiny text pointers | That is correct — they are in LFS. `git lfs ls-files` to confirm |
| `.env` changes ignored | `docker compose up -d` again; `env_file` is read at container creation |
