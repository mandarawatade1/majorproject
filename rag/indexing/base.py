"""The vector index protocol and the hit record it returns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from rag.chunking.base import Chunk, context_header


@dataclass(slots=True)
class IndexedHit:
    """One retrieved chunk and why it was retrieved."""

    chunk_id: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def search_text(self) -> str:
        """Content carrying the same context header the indexes were built from.

        A reranker can only judge what it is handed. Handed bare `content`, a
        cross-encoder was asked to score a table of course codes against a
        question naming a department that the table never spells out -- and so
        it ranked the department's own syllabus below a blog post whose title
        repeats the department name. The header was already sitting in the
        metadata; it simply never reached the stage that decides what survives.
        """
        meta = self.metadata or {}
        header = context_header(
            str(meta.get("document_title", "")), str(meta.get("section_path", ""))
        )
        return f"{header}\n\n{self.content}" if header else self.content

    @property
    def document_id(self) -> str:
        return str(self.metadata.get("document_id", ""))

    @property
    def is_demo(self) -> bool:
        return bool(self.metadata.get("is_demo", False))

    @property
    def page_number(self) -> int | None:
        page = self.metadata.get("page_number", -1)
        return None if page in (-1, None) else int(page)

    def citation_label(self) -> str:
        title = str(self.metadata.get("document_title") or self.document_id)
        section = str(self.metadata.get("section_path") or "")
        # section is built as "{document_title} > {heading} > ..." at parse
        # time, so it always starts with the title -- stripping that prefix
        # here is what stops "X > X > Mission" reaching a citation.
        if section.startswith(title):
            section = section[len(title):].lstrip(" >")
        parts = [title]
        if section:
            parts.append(section)
        if self.page_number is not None:
            parts.append(f"page {self.page_number}")
        label = " > ".join(parts)
        return f"{label} [DEMO DATA]" if self.is_demo else label


class VectorIndex(Protocol):
    """Stores chunk vectors and searches them.

    Chunk ids are the same UUIDs PostgreSQL holds, so the index carries no
    truth of its own — it is a derived structure that can be dropped and
    rebuilt from the database at any time.
    """

    name: str

    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> int: ...

    def search(
        self,
        vector: list[float],
        top_k: int,
        where: dict[str, Any] | None = None,
    ) -> list[IndexedHit]: ...

    def count(self) -> int: ...

    def reset(self) -> None: ...
