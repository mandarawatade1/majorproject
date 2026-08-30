"""C1's chunker: structure-aware, section-respecting.

C0 (fixed.py) splits blind to structure and therefore carries no section_path
or page_number on any chunk — not an oversight, an honest consequence of a
fixed window spanning arbitrary parts of a document. This chunker exists to
fix exactly that: it never lets a chunk cross a section boundary, and every
chunk it produces carries the section_path (and page_number, where the source
has pages) that a citation needs to point somewhere real.

It consumes `document.sections`, which the parser already builds — this module
does no heading detection of its own. Its job is entirely: (1) drop sections
that are navigation noise rather than content, (2) keep small sections whole,
(3) split large sections without breaking mid-paragraph where avoidable.

A section's page_number is carried as its `start_page` onto every chunk split
from it, not interpolated. If a section spans pages 4-6, every chunk from it
is labelled page 4. This is a known simplification, not a defect: attributing
sub-chunks to a page by character-offset guesswork would be a fabricated
precision the source doesn't support. Documented in Phase 4 notes rather than
silently done.
"""

from __future__ import annotations

from rag.chunking.base import Chunk
from rag.ingestion.models import ParsedDocument, Section


class StructureAwareChunker:
    """Chunk within section boundaries; never split across a heading."""

    name = "semantic"

    def __init__(self, max_size: int = 1024, overlap: int = 128) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        if overlap < 0:
            raise ValueError("overlap cannot be negative")
        if overlap >= max_size:
            raise ValueError(f"overlap ({overlap}) must be smaller than max_size ({max_size})")
        self.max_size = max_size
        self.overlap = overlap

    def chunk(self, document: ParsedDocument) -> list[Chunk]:
        sections = document.substantive_sections

        if not sections:
            if not document.text.strip():
                return []
            fallback = Section(
                heading=document.title,
                level=0,
                content=document.text,
                order_index=0,
                section_path=document.title,
            )
            sections = [fallback]

        chunks: list[Chunk] = []
        for section in sections:
            chunks.extend(self._chunk_section(document, section, start_index=len(chunks)))
        return chunks

    def _chunk_section(
        self, document: ParsedDocument, section: Section, start_index: int
    ) -> list[Chunk]:
        content = section.content.strip()
        if not content:
            return []

        section_path = section.section_path or section.heading

        if len(content) <= self.max_size:
            return [
                self._make_chunk(
                    document,
                    content,
                    chunk_index=start_index,
                    section_path=section_path,
                    page_number=section.start_page,
                    char_start=0,
                    char_end=len(content),
                )
            ]

        paragraphs = [p for p in content.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [content]

        pieces: list[str] = []
        buffer = ""
        for para in paragraphs:
            candidate = f"{buffer}\n\n{para}" if buffer else para
            if len(candidate) <= self.max_size:
                buffer = candidate
                continue

            if buffer:
                pieces.append(buffer)
            if len(para) <= self.max_size:
                buffer = para
            else:
                stride = self.max_size - self.overlap
                pos = 0
                while pos < len(para):
                    end = min(pos + self.max_size, len(para))
                    pieces.append(para[pos:end])
                    if end == len(para):
                        break
                    pos += stride
                buffer = ""
        if buffer:
            pieces.append(buffer)

        chunks: list[Chunk] = []
        cursor = 0
        for i, piece in enumerate(pieces):
            piece_start = content.find(piece, max(cursor - self.overlap, 0))
            if piece_start == -1:
                piece_start = cursor
            piece_end = piece_start + len(piece)
            chunks.append(
                self._make_chunk(
                    document,
                    piece,
                    chunk_index=start_index + i,
                    section_path=section_path,
                    page_number=section.start_page,
                    char_start=piece_start,
                    char_end=piece_end,
                )
            )
            cursor = piece_end
        return chunks

    def _make_chunk(
        self,
        document: ParsedDocument,
        content: str,
        *,
        chunk_index: int,
        section_path: str | None,
        page_number: int | None,
        char_start: int,
        char_end: int,
    ) -> Chunk:
        return Chunk(
            document_id=document.doc_id,
            chunk_index=chunk_index,
            content=content,
            document_title=document.title,
            source_url=document.source_url,
            section_path=section_path,
            page_number=page_number,
            is_demo=document.is_demo,
            char_start=char_start,
            char_end=char_end,
            metadata={"chunker": self.name},
        )
