"""The knowledge domain: documents, their section hierarchy, and chunks.

This is the persisted form of what `rag.ingestion` produces. Three properties
of the Phase 1 design are carried into the schema rather than left to
convention:

* **Provenance is not optional.** Every document has a `source_url` or a
  `local_path`, a `fetched_at`, and a `content_hash`. A check constraint
  enforces that at least one of the two location columns is present, so a
  document that cannot be traced back to anywhere cannot be inserted.
* **Structure survives.** `document_sections` is a self-referencing tree with a
  materialised `section_path`, and chunks point at the section they came from.
  This is what makes "structure-aware" a property of the stored data rather
  than a claim about the parser.
* **`is_demo` propagates.** It is set on the document at ingestion, denormalised
  onto every chunk, and read straight off the chunk when a citation is built.
  Retrieval never has to join back to the document to know whether it is about
  to cite synthetic data, which means the badge cannot be lost by a query that
  forgot the join.

Chunks are created in Phase 4. The table is defined now so that the schema is
settled before the chunker is written against it.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import DocumentCategory, IngestStatus, SourceType
from app.models.mixins import DemoMixin, pg_enum, pk


class Document(Base, TimestampMixin, DemoMixin):
    """One ingested document, as recorded in corpus/manifest.json."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "source_url IS NOT NULL OR local_path IS NOT NULL",
            name="ck_documents_has_provenance",
        ),
        Index("ix_documents_content_hash", "content_hash"),
        Index("ix_documents_category", "category"),
        Index("ix_documents_published_date", "published_date"),
        # Retrieval in "real sources only" mode filters on this constantly.
        Index("ix_documents_real_only", "id", postgresql_where=text("is_demo = false")),
    )

    id: Mapped[uuid.UUID] = pk()

    # The pipeline's identifier, e.g. "pce-about-the-institute" or the
    # real-world "DEMO/EXAM/2026/03". Unique, and the natural key the seed
    # loader upserts on.
    doc_id: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        pg_enum(SourceType, "source_type"), nullable=False
    )
    category: Mapped[DocumentCategory] = mapped_column(
        pg_enum(DocumentCategory, "document_category"),
        nullable=False,
        default=DocumentCategory.OTHER,
    )

    # --- Provenance ---
    source_url: Mapped[str | None] = mapped_column(Text)
    local_path: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # --- Descriptive ---
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL")
    )
    author: Mapped[str | None] = mapped_column(String(240))
    published_date: Mapped[date | None] = mapped_column(Date)
    page_count: Mapped[int | None] = mapped_column(Integer)
    word_count: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")

    # --- Pipeline state ---
    ingest_status: Mapped[IngestStatus] = mapped_column(
        pg_enum(IngestStatus, "ingest_status"), nullable=False, default=IngestStatus.PARSED
    )
    ingest_error: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    extra: Mapped[dict | None] = mapped_column(JSONB)

    sections: Mapped[list[DocumentSection]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class SuppressedDocument(Base, TimestampMixin):
    """A document dropped as a duplicate of another.

    Kept so the corpus can still answer "did you crawl this page?" with a yes
    and a pointer, rather than appearing never to have seen it. Mirrors
    `suppressed_duplicates` in the manifest.
    """

    __tablename__ = "suppressed_documents"
    __table_args__ = (Index("ix_suppressed_duplicate_of", "duplicate_of_doc_id"),)

    id: Mapped[uuid.UUID] = pk()
    doc_id: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(Text)
    duplicate_of_doc_id: Mapped[str] = mapped_column(String(200), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class DocumentSection(Base, TimestampMixin):
    """A node of a document's heading hierarchy.

    `section_path` is the breadcrumb shown in a citation. `start_page` is set
    for PDFs and is what makes page-level provenance possible; it is null for
    HTML, which has no pages.
    """

    __tablename__ = "document_sections"
    __table_args__ = (
        UniqueConstraint("document_id", "order_index", name="uq_section_document_order"),
        Index("ix_sections_document", "document_id"),
        Index("ix_sections_parent", "parent_section_id"),
    )

    id: Mapped[uuid.UUID] = pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    parent_section_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("document_sections.id", ondelete="CASCADE")
    )
    heading: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    section_path: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    char_count: Mapped[int | None] = mapped_column(Integer)
    start_page: Mapped[int | None] = mapped_column(Integer)
    end_page: Mapped[int | None] = mapped_column(Integer)

    document: Mapped[Document] = relationship(back_populates="sections")
    children: Mapped[list[DocumentSection]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )
    parent: Mapped[DocumentSection | None] = relationship(
        back_populates="children", remote_side="DocumentSection.id"
    )


class Chunk(Base, TimestampMixin, DemoMixin):
    """A retrievable unit. Populated in Phase 4.

    `parent_chunk_id` implements small-to-big retrieval: search matches the
    precise child, generation receives the fuller parent. The vector itself
    lives in Chroma keyed by this row's `id`; PostgreSQL holds the source of
    truth and Chroma holds only the index, so the corpus can be rebuilt from
    the database if the vector store is lost.
    """

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunk_document_index"),
        Index("ix_chunks_document", "document_id"),
        Index("ix_chunks_section", "section_id"),
        Index("ix_chunks_parent", "parent_chunk_id"),
        Index("ix_chunks_metadata", "chunk_metadata", postgresql_using="gin"),
        Index("ix_chunks_real_only", "id", postgresql_where=text("is_demo = false")),
    )

    id: Mapped[uuid.UUID] = pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("document_sections.id", ondelete="SET NULL")
    )
    parent_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL")
    )

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_summary: Mapped[str | None] = mapped_column(Text)
    hypothetical_questions: Mapped[list[str] | None] = mapped_column(JSONB)

    token_count: Mapped[int | None] = mapped_column(Integer)
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)

    # Denormalised from the section so a citation can be built without a join.
    section_path: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)

    embedding_model: Mapped[str | None] = mapped_column(String(120))
    chunk_metadata: Mapped[dict | None] = mapped_column(JSONB)

    document: Mapped[Document] = relationship(back_populates="chunks")


__all__ = ["Chunk", "Document", "DocumentSection", "SuppressedDocument"]
