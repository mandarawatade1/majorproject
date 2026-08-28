"""Write parsed documents to corpus/normalised/ in a stable, reviewable form.

Two files per document:

    <doc_id>.md    front matter + body, with section markers. Human-readable,
                   diffable, and what a supervisor can open to check the
                   corpus by eye.
    <doc_id>.json  the full structured record, including every section with
                   its heading path and page range. This is what Phase 2 loads
                   into PostgreSQL and Phase 4 chunks.

Validation runs before anything is written. A document that fails its
invariants is reported and skipped rather than written, so the corpus on disk
is always sound.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from rag.ingestion.models import ParsedDocument


@dataclass
class NormaliseResult:
    written: list[str] = field(default_factory=list)
    rejected: list[tuple[str, list[str]]] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.written) + len(self.unchanged)


def normalise(
    documents: list[ParsedDocument],
    output_dir: Path,
    *,
    force: bool = False,
    prune: bool = True,
) -> NormaliseResult:
    """Validate and write documents, then remove anything else.

    Pruning is not housekeeping — it is what makes the directory *mean*
    something. Without it, normalise only ever added: a document dropped by
    deduplication, or one that stopped being crawled, kept its file forever.
    The first deduplicating run suppressed 214 documents and 200 of them
    survived on disk, so `load_documents` read them straight back and the
    manifest reported a corpus that still contained every duplicate. The
    deduplication was, in effect, a no-op.

    The directory is a generated artefact and is gitignored, so it is safe to
    treat as derived state: after this call it contains exactly the documents
    passed in, and nothing else.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    result = NormaliseResult()

    for document in documents:
        problems = document.validate()
        if problems:
            result.rejected.append((document.doc_id or "<no id>", problems))
            continue

        json_path = output_dir / f"{document.file_stem}.json"
        if not force and _hash_unchanged(json_path, document.content_hash):
            result.unchanged.append(document.doc_id)
            continue

        (output_dir / f"{document.file_stem}.md").write_text(
            _to_markdown(document), encoding="utf-8"
        )
        json_path.write_text(
            json.dumps(document.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        result.written.append(document.doc_id)

    if prune and documents:
        # `documents` is empty when a parse failed outright. Pruning then would
        # delete the whole corpus on the strength of a broken run, so don't.
        result.pruned = _prune(output_dir, documents)

    return result


def _prune(output_dir: Path, documents: list[ParsedDocument]) -> list[str]:
    """Delete outputs for documents no longer in the corpus."""
    expected = {d.file_stem for d in documents}
    removed: list[str] = []
    for path in sorted(output_dir.iterdir()):
        if path.suffix not in (".json", ".md") or path.stem in expected:
            continue
        try:
            path.unlink()
            removed.append(path.name)
        except OSError:
            continue
    return removed


def _hash_unchanged(json_path: Path, content_hash: str) -> bool:
    """Skip rewriting a document whose extracted text has not changed."""
    if not json_path.exists():
        return False
    try:
        existing = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(existing.get("content_hash") == content_hash)


def _to_markdown(document: ParsedDocument) -> str:
    """Front matter plus body, with an explicit marker per section.

    The markers are not decoration: they let a reader confirm by eye that the
    structure-aware chunker split where the document actually changes topic.
    """
    lines = [
        "---",
        f"doc_id: {document.doc_id}",
        f"title: {json.dumps(document.title, ensure_ascii=False)}",
        f"category: {document.category.value}",
        f"source_type: {document.source_type.value}",
        f"source_url: {document.source_url or ''}",
        f"local_path: {document.local_path or ''}",
        f"fetched_at: {document.fetched_at}",
        f"content_hash: {document.content_hash}",
        f"department: {document.department or ''}",
        f"published_date: {document.published_date or ''}",
        f"page_count: {document.page_count if document.page_count is not None else ''}",
        f"word_count: {document.word_count}",
        f"section_count: {len(document.sections)}",
        f"is_demo: {str(document.is_demo).lower()}",
    ]
    if document.is_demo:
        lines.append(f"demo_reason: {json.dumps(document.demo_reason, ensure_ascii=False)}")
    lines.append("---")
    lines.append("")

    if document.is_demo:
        lines.append("> **DEMO DATA** — this document is synthetic. It does not")
        lines.append("> describe any real institutional fact, person or figure.")
        lines.append("")

    lines.append(f"# {document.title}")
    lines.append("")

    if not document.sections:
        lines.append(document.text)
        return "\n".join(lines)

    for section in document.sections:
        pages = ""
        if section.start_page is not None:
            pages = (
                f", page {section.start_page}"
                if section.start_page == section.end_page
                else f", pages {section.start_page}-{section.end_page}"
            )
        lines.append(f"<!-- section: {section.section_path}{pages} -->")
        lines.append(f"{'#' * min(section.level + 1, 6)} {section.heading}")
        lines.append("")
        lines.append(section.content)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
