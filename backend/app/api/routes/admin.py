"""Administrative endpoints. Every route here requires an admin account.

Scope is what an administrator needs in order to trust the system rather than
everything that could be automated: see what the corpus and indexes actually
contain, see what the evaluation produced, and rebuild an index without opening
a terminal. Crawling and content editing belong to the admin console phase.

The rebuild endpoint is the one with teeth, and it is treated accordingly: it
destroys an index, it takes several minutes, and on this hardware it competes
for memory with everything else. It therefore requires an explicit typed
confirmation, refuses to start while another rebuild is running, and reports
progress rather than blocking the request.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from app.core.logging import get_logger
from app.models.institutional import Announcement, Department, Faculty, Program
from app.models.knowledge import Chunk, Document, DocumentSection
from fastapi import APIRouter, Body, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import AdminUser, DbSession

logger = get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

CORPUS_ROOT = Path("/corpus")
EVAL_ROOT = Path("/app/eval/results")


# ---------------------------------------------------------------------------
# What the system holds
# ---------------------------------------------------------------------------


def _manifest_documents() -> int | None:
    """How many documents the manifest says the corpus holds.

    The manifest is the definition of the corpus: the ingestion CLI writes it,
    the indexer reads the same `normalised/` directory it describes, and the
    report quotes its statistics. The database is a *copy*, loaded by
    `python -m app.seed corpus`. Nothing re-runs that seed when the corpus is
    regenerated, so the copy can fall behind the original silently — and when
    it does, the portal serves one set of documents while Ask PCE answers from
    another. That is the specific failure this endpoint exists to make visible,
    so the comparison is computed here rather than left to the reader.
    """
    try:
        raw = json.loads((CORPUS_ROOT / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    documents = raw.get("documents")
    if isinstance(documents, list):
        return len(documents)
    statistics = raw.get("statistics") or {}
    total = statistics.get("total_documents")
    return total if isinstance(total, int) else None


@router.get("/corpus", summary="Corpus and index contents")
def corpus_detail(_: AdminUser, db: DbSession) -> dict[str, Any]:
    """What the database holds, what the manifest defines, what the index contains.

    All three describe the same corpus and should agree. When they do not — a
    corpus regenerated without re-seeding, an index built from a different
    document set, a seed that half-completed — every answer the system gives is
    computed over something other than what the database describes, and nothing
    else in the system will say so.
    """
    documents = db.scalar(select(func.count()).select_from(Document)) or 0
    demo = (
        db.scalar(select(func.count()).select_from(Document).where(Document.is_demo.is_(True))) or 0
    )
    sections = db.scalar(select(func.count()).select_from(DocumentSection)) or 0
    chunk_rows = db.scalar(select(func.count()).select_from(Chunk)) or 0

    by_category = db.execute(
        select(Document.category, func.count())
        .group_by(Document.category)
        .order_by(func.count().desc())
    ).all()

    index: dict[str, Any] = {}
    try:
        from rag.config import get_config
        from rag.factory import build_index, build_sparse_index

        dense = build_index("", get_config("C3").chunking.value)
        index["dense"] = {"name": dense.name, "vectors": dense.count()}
        sparse = build_sparse_index()
        index["sparse"] = {"name": sparse.name, "entries": sparse.count()}
    except Exception as exc:  # noqa: BLE001 - reported, never fatal
        index["error"] = str(exc)

    manifest_documents = _manifest_documents()
    if manifest_documents is None:
        corpus_agreement: dict[str, Any] = {"error": f"no readable manifest at {CORPUS_ROOT}"}
    else:
        corpus_agreement = {
            "manifest_documents": manifest_documents,
            "database_documents": documents,
            "agree": manifest_documents == documents,
        }
        drift = documents - manifest_documents
        if drift < 0:
            corpus_agreement["difference"] = f"{-drift} missing from the database"
            corpus_agreement["action"] = (
                f"{-drift} documents the manifest defines are not in the database. Run "
                "`python -m app.seed corpus` to load them. Until then the portal serves "
                "fewer documents than retrieval can cite."
            )
        elif drift > 0:
            # The two directions are different faults and want different
            # answers. Missing rows are a seed that has not been run. Extra
            # rows are documents the corpus no longer contains, and re-running
            # the seed will not clear them: `load_corpus` inserts and updates,
            # and the only delete it issues is for the sections of a document
            # it is already updating. Nothing removes a Document whose source
            # file has gone.
            corpus_agreement["difference"] = f"{drift} in the database but not the manifest"
            corpus_agreement["action"] = (
                f"{drift} documents in the database are absent from the manifest — rows left "
                "behind by an earlier corpus. Re-seeding will NOT remove them: the seeder "
                "never deletes documents. The portal will list documents that retrieval "
                "cannot cite, because the index was built from the manifest."
            )

    return {
        "database": {
            "documents": documents,
            "real": documents - demo,
            "demo": demo,
            "real_share": round((documents - demo) / documents, 4) if documents else None,
            "sections": sections,
            "by_category": {str(c.value): n for c, n in by_category},
        },
        "corpus_agreement": corpus_agreement,
        "index": index,
        # Reported apart from the document counts, and with its meaning
        # attached, because a bare `chunks: 0` beside them reads as a failed
        # load. Chunks are never written to PostgreSQL: `rag.chunking` builds
        # its own `Chunk` — a different class that happens to share the name —
        # and passes it to the vector store. The counts that matter are under
        # `index`. Zero here is the expected value.
        "chunk_table": {
            "rows": chunk_rows,
            "note": (
                "expected to be 0 — the chunks table is declared in the schema but "
                "nothing writes to it; chunk storage is the vector and BM25 indexes"
            ),
        },
        "reference_data": {
            "departments": db.scalar(select(func.count()).select_from(Department)) or 0,
            "programs": db.scalar(select(func.count()).select_from(Program)) or 0,
            "faculty": db.scalar(select(func.count()).select_from(Faculty)) or 0,
            "announcements": db.scalar(select(func.count()).select_from(Announcement)) or 0,
        },
    }


@router.get("/evaluations", summary="Evaluation runs on disk")
def evaluations(_: AdminUser) -> dict[str, Any]:
    """Summarise `eval/results/`, one entry per configuration.

    Read from disk rather than a table because the harness writes files and the
    files are what the report cites. A database copy would be a second source
    of truth that could disagree with the evidence.
    """
    if not EVAL_ROOT.exists():
        return {"root": str(EVAL_ROOT), "runs": [], "note": "no results directory"}

    runs: list[dict[str, Any]] = []
    for directory in sorted(p for p in EVAL_ROOT.iterdir() if p.is_dir()):
        answers = sorted(directory.glob("q*.txt"))
        summary = directory / "summary.csv"
        verdicts: dict[str, int] = {}
        stops: dict[str, int] = {}

        for path in answers:
            text = path.read_text(errors="replace")
            start = text.find("\n{")
            if start == -1:
                continue
            try:
                log = json.loads(text[start:])
            except json.JSONDecodeError:
                continue
            verdict = ((log.get("verification") or {}).get("verdict")) or None
            if verdict:
                verdicts[verdict] = verdicts.get(verdict, 0) + 1
            stop = ((log.get("retrieval") or {}).get("stop_reason")) or None
            if stop:
                stops[stop] = stops.get(stop, 0) + 1

        runs.append(
            {
                "config": directory.name,
                "questions": len(answers),
                "has_summary": summary.exists(),
                "modified": datetime.fromtimestamp(directory.stat().st_mtime, tz=UTC).isoformat(),
                "verification_verdicts": verdicts or None,
                "agent_stop_reasons": stops or None,
            }
        )

    return {"root": str(EVAL_ROOT), "runs": runs}


# ---------------------------------------------------------------------------
# Rebuilding an index
# ---------------------------------------------------------------------------


class RebuildRequest(BaseModel):
    config: str = Field(default="C3", description="Configuration whose chunker to use")
    confirm: str = Field(
        description="Must be the literal string REBUILD. Guards against a "
        "misdirected click destroying an index that takes minutes to restore."
    )
    limit: int = Field(default=0, ge=0, description="Index only the first N documents")


class _RebuildState:
    """Progress of the one rebuild this process will run at a time."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.running = False
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.config: str | None = None
        self.result: str | None = None
        self.error: str | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "config": self.config,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "error": self.error,
        }


_rebuild = _RebuildState()


def _run_rebuild(config_name: str, limit: int) -> None:
    from rag.config import get_config
    from rag.factory import build_pipeline
    from rag.ingestion.manifest import load_documents

    try:
        config = get_config(config_name)
        documents = load_documents(CORPUS_ROOT / "normalised")
        if limit:
            documents = documents[:limit]

        pipeline = build_pipeline(config)
        pipeline.index.reset()
        # The sparse index must be reset with the dense one. Chunk identifiers
        # are regenerated per run, so a surviving sparse index shares no ids
        # with the rebuilt dense one and RRF silently stops fusing.
        if pipeline.sparse_index is not None:
            pipeline.sparse_index.reset()

        report = pipeline.index_documents(documents)
        _rebuild.result = report.summary()
        logger.info("rebuild_finished", config=config_name, summary=report.summary())
    except Exception as exc:  # noqa: BLE001 - surfaced through the status endpoint
        _rebuild.error = str(exc)
        logger.exception("rebuild_failed", config=config_name)
    finally:
        _rebuild.finished_at = datetime.now(UTC).isoformat()
        _rebuild.running = False


@router.post("/index/rebuild", summary="Re-chunk and re-index the corpus")
def rebuild_index(
    admin: AdminUser,
    payload: Annotated[RebuildRequest, Body()],
) -> dict[str, Any]:
    if payload.confirm != "REBUILD":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="set `confirm` to REBUILD to proceed; this destroys the index",
        )

    with _rebuild.lock:
        if _rebuild.running:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"a rebuild of {_rebuild.config} is already running",
            )
        _rebuild.running = True
        _rebuild.config = payload.config
        _rebuild.started_at = datetime.now(UTC).isoformat()
        _rebuild.finished_at = None
        _rebuild.result = None
        _rebuild.error = None

    logger.warning(
        "rebuild_started",
        config=payload.config,
        by=str(admin.id),
        limit=payload.limit or None,
    )
    threading.Thread(
        target=_run_rebuild,
        args=(payload.config, payload.limit),
        name="index-rebuild",
        daemon=True,
    ).start()

    return {
        "accepted": True,
        "note": "rebuilding in the background; poll /admin/index/status",
        **_rebuild.snapshot(),
    }


@router.get("/index/status", summary="Progress of the current or last rebuild")
def rebuild_status(_: AdminUser) -> dict[str, Any]:
    return _rebuild.snapshot()
