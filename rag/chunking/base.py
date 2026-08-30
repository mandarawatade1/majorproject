"""The chunk record and the protocol every chunker satisfies."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from rag.ingestion.models import ParsedDocument


@dataclass(slots=True)
class Chunk:
    """A retrievable unit, before it is embedded or persisted.

    Mirrors the `chunks` table. `is_demo`, `section_path` and `page_number` are
    denormalised onto it deliberately: a citation is built from a chunk alone,
    so anything a citation must show has to be carried here rather than fetched
    by a join that a caller might forget.
    """

    document_id: str
    chunk_index: int
    content: str

    chunk_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    section_id: str | None = None
    parent_chunk_id: str | None = None

    # Carried so a citation needs nothing else.
    document_title: str = ""
    source_url: str | None = None
    section_path: str | None = None
    page_number: int | None = None
    is_demo: bool = False

    char_start: int | None = None
    char_end: int | None = None
    token_count: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        return len(self.content)

    def citation_label(self) -> str:
        """How this chunk identifies itself in a source list.

        Page numbers appear when the source has them, which is what makes the
        page-level provenance requirement visible to a reader rather than only
        present in the database.

        `section_path` is built as "{document_title} > {heading} > ..." at
        parse time, so it always starts with the title, not just occasionally
        equals it. Stripping that leading title here -- rather than a bare
        equality check -- is what stops "Program Overview > Program Overview
        > Mission" from reaching a citation.
        """
        title = self.document_title or self.document_id
        path = self.section_path or ""
        if path.startswith(title):
            path = path[len(title):].lstrip(" >")
        parts = [title]
        if path:
            parts.append(path)
        if self.page_number is not None:
            parts.append(f"page {self.page_number}")
        label = " > ".join(parts)
        return f"{label} [DEMO DATA]" if self.is_demo else label

    def to_metadata(self) -> dict[str, Any]:
        """Flat metadata for the vector store. Chroma accepts only scalars."""
        return {
            "document_id": self.document_id,
            "document_title": self.document_title,
            "chunk_index": self.chunk_index,
            "source_url": self.source_url or "",
            "section_path": self.section_path or "",
            "page_number": self.page_number if self.page_number is not None else -1,
            "is_demo": self.is_demo,
        }


class Chunker(Protocol):
    """Turns a parsed document into chunks.

    One method, so C0's fixed splitter and Phase 4's structure-aware splitter
    are interchangeable from the orchestrator's point of view.
    """

    name: str

    def chunk(self, document: ParsedDocument) -> list[Chunk]: ...
