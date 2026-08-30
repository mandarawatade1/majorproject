"""C0's chunker: fixed-size character windows.

Deliberately naive. It ignores headings, splits mid-sentence, and knows nothing
about the document's structure — which is exactly the behaviour the project
claims to improve on.

It is still written properly rather than as a strawman. A baseline built
carelessly makes the proposed system look better for the wrong reason, and an
examiner who notices that discounts every number in Chapter 4. So the overlap
works, boundaries are stable, and no content is dropped: it is the best honest
version of a naive approach.
"""

from __future__ import annotations

from rag.chunking.base import Chunk
from rag.ingestion.models import ParsedDocument


class FixedSizeChunker:
    """Split text every `size` characters with `overlap` characters of carry-over."""

    name = "fixed"

    def __init__(self, size: int = 512, overlap: int = 64) -> None:
        if size <= 0:
            raise ValueError("chunk size must be positive")
        if overlap < 0:
            raise ValueError("overlap cannot be negative")
        if overlap >= size:
            # Otherwise the window never advances and the loop does not end.
            raise ValueError(f"overlap ({overlap}) must be smaller than size ({size})")
        self.size = size
        self.overlap = overlap

    def chunk(self, document: ParsedDocument) -> list[Chunk]:
        text = document.text
        if not text.strip():
            return []

        stride = self.size - self.overlap
        chunks: list[Chunk] = []
        start = 0

        while start < len(text):
            end = min(start + self.size, len(text))
            content = text[start:end]

            if content.strip():
                chunks.append(
                    Chunk(
                        document_id=document.doc_id,
                        chunk_index=len(chunks),
                        content=content,
                        document_title=document.title,
                        source_url=document.source_url,
                        # C0 carries no section path and no page number. Not an
                        # oversight: a fixed window spans arbitrary parts of a
                        # document, so there is no single section or page it
                        # honestly belongs to. That absence is precisely what
                        # structure-aware chunking fixes in C1.
                        section_path=None,
                        page_number=None,
                        is_demo=document.is_demo,
                        char_start=start,
                        char_end=end,
                        metadata={"chunker": self.name},
                    )
                )

            if end == len(text):
                break
            start += stride

        return chunks
