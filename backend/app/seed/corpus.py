"""Load the Phase 1 corpus into PostgreSQL.

Reads `corpus/manifest.json` and `corpus/normalised/*.json` — the outputs of
`python -m rag.ingestion` — and writes `documents`, `document_sections` and
`suppressed_documents`.

Two properties matter more than speed:

**Idempotent.** Keyed on `doc_id`, so running it twice is the same as running
it once. A document whose `content_hash` is unchanged is skipped entirely; one
whose hash has moved has its sections replaced wholesale rather than merged,
because a re-parse can renumber every section and a partial merge would leave
orphans pointing at headings that no longer exist.

**`is_demo` is copied, never inferred.** The value comes from the manifest,
which got it from the parser, which refused to mark an internal-only category
as real. Nothing in this module decides whether a document is demo data; it
only carries the decision forward.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.enums import DocumentCategory, IngestStatus, SourceType
from app.models.institutional import Department
from app.models.knowledge import Document, DocumentSection, SuppressedDocument


@dataclass
class LoadReport:
    manifest_total: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    suppressed: int = 0
    sections: int = 0
    skipped: list[str] = field(default_factory=list)

    @property
    def accounted_for(self) -> int:
        """Documents this run actually put in, or confirmed already in, the DB."""
        return self.inserted + self.updated + self.unchanged

    @property
    def is_complete(self) -> bool:
        return self.accounted_for == self.manifest_total

    def summary(self) -> str:
        return (
            f"documents: {self.inserted} inserted, {self.updated} updated, "
            f"{self.unchanged} unchanged | sections: {self.sections} | "
            f"suppressed rows: {self.suppressed}"
        )


def load_corpus(session: Session, corpus_dir: Path) -> LoadReport:
    """Load manifest + normalised documents. Returns what changed."""
    manifest_path = corpus_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"{manifest_path} not found. Run `python -m rag.ingestion parse` and "
            f"`... manifest` before seeding."
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    normalised_dir = corpus_dir / "normalised"
    report = LoadReport(manifest_total=len(manifest.get("documents", [])))

    departments = {d.name: d.id for d in session.scalars(select(Department))}

    for row in manifest.get("documents", []):
        _load_one(session, row, normalised_dir, departments, report)

    report.suppressed = _load_suppressed(session, manifest.get("suppressed_duplicates", []))
    session.flush()
    return report


# ---------------------------------------------------------------------------


def _load_one(
    session: Session,
    row: dict[str, Any],
    normalised_dir: Path,
    departments: dict[str, Any],
    report: LoadReport,
) -> None:
    doc_id = row["doc_id"]
    existing = session.scalar(select(Document).where(Document.doc_id == doc_id))

    if existing is not None and existing.content_hash == row["content_hash"]:
        report.unchanged += 1
        return

    payload = _read_normalised(normalised_dir, doc_id, row.get("file_stem"))
    if payload is None:
        report.skipped.append(
            f"{doc_id}: no normalised .json on disk "
            f"(looked for {row.get('file_stem') or '<derived stem>'}.json)"
        )
        return

    fields = _document_fields(row, payload, departments)

    if existing is None:
        document = Document(doc_id=doc_id, **fields)
        session.add(document)
        session.flush()
        report.inserted += 1
    else:
        for key, value in fields.items():
            setattr(existing, key, value)
        # Replace rather than merge: a re-parse can renumber every section, and
        # merging would leave rows pointing at headings that no longer exist.
        session.execute(delete(DocumentSection).where(DocumentSection.document_id == existing.id))
        session.flush()
        document = existing
        report.updated += 1

    report.sections += _load_sections(session, document, payload.get("sections", []))


def _document_fields(
    row: dict[str, Any], payload: dict[str, Any], departments: dict[str, Any]
) -> dict[str, Any]:
    return {
        "title": (row.get("title") or payload.get("title") or "Untitled")[:500],
        "source_type": SourceType(row["source_type"]),
        "category": _category(row.get("category")),
        "source_url": row.get("source_url"),
        "local_path": row.get("local_path"),
        "fetched_at": _datetime(row.get("fetched_at")),
        "content_hash": row["content_hash"],
        "department_id": departments.get(row.get("department") or ""),
        "author": payload.get("author"),
        "published_date": _date(row.get("published_date")),
        "page_count": row.get("page_count"),
        "word_count": row.get("word_count"),
        "language": payload.get("language") or "en",
        "ingest_status": IngestStatus.PARSED,
        # Copied from the manifest. Never inferred here.
        "is_demo": bool(row.get("is_demo", False)),
        "demo_reason": row.get("demo_reason"),
    }


def _load_sections(session: Session, document: Document, sections: list[dict[str, Any]]) -> int:
    """Insert sections, then wire up parents in a second pass.

    Two passes because a section's parent may appear after it in the list, and
    the foreign key needs a row that already exists.
    """
    created: list[DocumentSection] = []
    for payload in sections:
        section = DocumentSection(
            document_id=document.id,
            heading=payload.get("heading") or "",
            level=int(payload.get("level") or 1),
            section_path=payload.get("section_path") or "",
            order_index=int(payload.get("order_index") or len(created)),
            content=payload.get("content"),
            char_count=len(payload.get("content") or ""),
            start_page=payload.get("start_page"),
            end_page=payload.get("end_page"),
        )
        session.add(section)
        created.append(section)

    session.flush()

    for payload, section in zip(sections, created, strict=True):
        parent_index = payload.get("parent_index")
        if parent_index is not None and 0 <= int(parent_index) < len(created):
            section.parent_section_id = created[int(parent_index)].id

    session.flush()
    return len(created)


def _load_suppressed(session: Session, rows: list[dict[str, Any]]) -> int:
    """Record the duplicates the pipeline dropped.

    A suppressed page must still be answerable as "yes, we crawled it", so the
    URL survives here even though its content does not.
    """
    if not rows:
        return 0

    existing = {d.doc_id for d in session.scalars(select(SuppressedDocument))}
    added = 0
    for row in rows:
        if row.get("doc_id") in existing:
            continue
        session.add(
            SuppressedDocument(
                doc_id=row["doc_id"],
                title=(row.get("title") or "")[:500] or None,
                source_url=row.get("source_url"),
                duplicate_of_doc_id=row["duplicate_of"],
                content_hash=row.get("content_hash") or "",
            )
        )
        added += 1
    return added


# ---------------------------------------------------------------------------
# Parsing helpers — tolerant, because a bad field should skip a document rather
# than abort a load of eight hundred.
# ---------------------------------------------------------------------------


def _read_normalised(
    normalised_dir: Path, doc_id: str, file_stem: str | None = None
) -> dict[str, Any] | None:
    """Find a document's .json by the stem the pipeline actually wrote it under.

    `file_stem` comes from the manifest. It is passed in rather than derived
    because doc_id -> filename is lossy: slugify truncates at 80 characters, so
    re-deriving it produces the wrong name for any longer id. An earlier version
    of this function did re-derive it, without the truncation, and silently
    skipped all 27 documents whose doc_id exceeded 80 characters.

    The fallback exists only for manifests written before `file_stem` was
    recorded, and it calls the pipeline's own slugify rather than
    reimplementing it — the whole point being that this transformation is
    defined in exactly one place.
    """
    if not file_stem:
        from rag.ingestion.models import slugify

        file_stem = slugify(doc_id.replace("/", "-"))

    path = normalised_dir / f"{file_stem}.json"
    if not path.exists():
        return None
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None


def _category(value: str | None) -> DocumentCategory:
    try:
        return DocumentCategory(value or "other")
    except ValueError:
        return DocumentCategory.OTHER


def _datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


__all__ = ["LoadReport", "load_corpus"]
