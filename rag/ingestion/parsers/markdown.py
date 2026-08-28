"""Demo corpus loader — the gatekeeper for synthetic data.

Every file under corpus/demo/ must carry YAML front matter declaring what it
is and why it is synthetic. A file without it is REJECTED, not defaulted.

That strictness is the whole point. `is_demo` propagates from here into the
database, into every chunk, and into every citation the user sees. If a
synthetic document could slip through unlabelled, the 80/20 real-versus-demo
claim would be decoration rather than a guarantee — and an examiner would be
right to distrust every number in Chapter 4.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rag.ingestion.models import DocumentCategory, ParsedDocument, SourceType, slugify
from rag.ingestion.parsers.sections import sections_from_markdown

REQUIRED_KEYS = ("title", "doc_id", "is_demo", "demo_reason", "category")

_FENCE = "---"


class DemoFrontMatterError(ValueError):
    """Raised when a demo document is missing or misusing its front matter."""


def parse_demo_markdown(path: Path) -> ParsedDocument:
    """Load one demo document. Raises DemoFrontMatterError if non-compliant."""
    raw = path.read_text(encoding="utf-8")
    meta, body = _split_front_matter(raw, path)

    missing = [key for key in REQUIRED_KEYS if key not in meta]
    if missing:
        raise DemoFrontMatterError(
            f"{path.name}: front matter is missing required key(s): {', '.join(missing)}. "
            f"Required: {', '.join(REQUIRED_KEYS)}."
        )

    if meta["is_demo"] is not True:
        raise DemoFrontMatterError(
            f"{path.name}: is_demo must be literally true. Everything under "
            f"corpus/demo/ is synthetic by definition; a file that is not demo "
            f"data does not belong in this folder."
        )

    reason = str(meta.get("demo_reason", "")).strip()
    if len(reason) < 20:
        raise DemoFrontMatterError(
            f"{path.name}: demo_reason must explain why this document is synthetic "
            f"(at least 20 characters). Got: {reason!r}"
        )

    try:
        category = DocumentCategory(str(meta["category"]))
    except ValueError as exc:
        valid = ", ".join(c.value for c in DocumentCategory)
        raise DemoFrontMatterError(
            f"{path.name}: unknown category {meta['category']!r}. Valid: {valid}"
        ) from exc

    if not body.strip():
        raise DemoFrontMatterError(f"{path.name}: document body is empty.")

    title = str(meta["title"]).strip()
    return ParsedDocument(
        doc_id=str(meta["doc_id"]).strip() or f"demo-{slugify(path.stem)}",
        title=title,
        source_type=SourceType.LOCAL_MARKDOWN,
        category=category,
        text=body.strip(),
        sections=sections_from_markdown(body, root_title=title),
        source_url=None,
        local_path=str(path),
        fetched_at=datetime.now(UTC).isoformat(),
        department=_optional_str(meta.get("department")),
        published_date=_optional_str(meta.get("created")),
        author=_optional_str(meta.get("author")),
        is_demo=True,
        demo_reason=reason,
        extra={"demo_identifier": _optional_str(meta.get("doc_id"))},
    )


def load_demo_corpus(demo_dir: Path) -> tuple[list[ParsedDocument], list[str]]:
    """Load every demo document. Returns (documents, errors).

    Errors are collected rather than raised so one malformed file reports
    clearly instead of aborting the whole ingest.
    """
    documents: list[ParsedDocument] = []
    errors: list[str] = []

    for path in sorted(demo_dir.rglob("*.md")):
        if path.name.upper().startswith("README"):
            continue
        try:
            documents.append(parse_demo_markdown(path))
        except DemoFrontMatterError as exc:
            errors.append(str(exc))
        except Exception as exc:  # noqa: BLE001 - report, do not abort
            errors.append(f"{path.name}: {type(exc).__name__}: {exc}")

    return documents, errors


# ---------------------------------------------------------------------------


def _split_front_matter(raw: str, path: Path) -> tuple[dict[str, Any], str]:
    stripped = raw.lstrip("﻿").lstrip()
    if not stripped.startswith(_FENCE):
        raise DemoFrontMatterError(
            f"{path.name}: no YAML front matter. Every file in corpus/demo/ must "
            f"begin with a '---' block declaring at least: {', '.join(REQUIRED_KEYS)}. "
            f"See corpus/demo/README.md."
        )

    parts = stripped.split(_FENCE, 2)
    if len(parts) < 3:
        raise DemoFrontMatterError(f"{path.name}: front matter block is not closed with '---'.")

    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("PyYAML is required: pip install pyyaml") from exc

    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        raise DemoFrontMatterError(f"{path.name}: front matter is not valid YAML: {exc}") from exc

    if not isinstance(meta, dict):
        raise DemoFrontMatterError(f"{path.name}: front matter must be a YAML mapping.")

    return meta, parts[2]


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = ["DemoFrontMatterError", "REQUIRED_KEYS", "load_demo_corpus", "parse_demo_markdown"]
