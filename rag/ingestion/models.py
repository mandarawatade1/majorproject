"""The data model every parser produces and every consumer reads.

One rule governs this module: a document is never separated from its
provenance. `source_url`, `fetched_at`, `content_hash` and `is_demo` travel
with the document into normalisation, into the database, into retrieval, and
finally into the citation a user sees. Research gap 4 (inadequate grounding and
explainability) is closed here, not in the prompt.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class SourceType(StrEnum):
    """Where a document's bytes came from."""

    WEB_HTML = "web_html"
    WEB_PDF = "web_pdf"
    LOCAL_MARKDOWN = "local_markdown"


class DocumentCategory(StrEnum):
    """What a document is about.

    Drives metadata filtering at retrieval time: a question about intake should
    search PROGRAMME and ADMISSION, not twenty years of event announcements.
    """

    # --- Real, public categories ---
    INSTITUTE_PROFILE = "institute_profile"
    ACCREDITATION = "accreditation"
    PROGRAMME = "programme"
    CURRICULUM = "curriculum"
    DEPARTMENT = "department"
    FACULTY = "faculty"
    RESEARCH = "research"
    LIBRARY = "library"
    STUDENT_LIFE = "student_life"
    PLACEMENT = "placement"
    ADMISSION = "admission"
    ANNOUNCEMENT = "announcement"
    EVENT = "event"
    REPORT = "report"
    GOVERNANCE = "governance"
    CONTACT = "contact"
    ALUMNI = "alumni"

    # --- Demo-only categories: internal material no institution publishes ---
    INTERNAL_WIKI = "internal_wiki"
    SOP = "sop"
    CIRCULAR = "circular"
    LAB_MANUAL = "lab_manual"
    HELPDESK = "helpdesk"
    TIMETABLE = "timetable"

    OTHER = "other"

    @property
    def is_internal_only(self) -> bool:
        """True for categories that can only ever be demo data.

        If a document in one of these categories is ever marked is_demo=False,
        something has gone wrong: this material is not public anywhere.
        """
        return self in {
            DocumentCategory.INTERNAL_WIKI,
            DocumentCategory.SOP,
            DocumentCategory.CIRCULAR,
            DocumentCategory.LAB_MANUAL,
            DocumentCategory.HELPDESK,
            DocumentCategory.TIMETABLE,
        }


@dataclass(slots=True)
class Section:
    """One node of a document's heading hierarchy.

    `section_path` is the breadcrumb a citation shows the user, e.g.
    "Academics > B.Tech > Computer Engineering > Curriculum". `start_page` is
    set for PDFs and is what makes page-level provenance possible; it is None
    for HTML, which has no pages.
    """

    heading: str
    level: int
    content: str
    order_index: int
    section_path: str = ""
    parent_index: int | None = None
    start_page: int | None = None
    end_page: int | None = None

    @property
    def char_count(self) -> int:
        return len(self.content)

    @property
    def is_substantive(self) -> bool:
        """False for headings with no body — navigation stubs, mostly."""
        return self.char_count >= 40


@dataclass(slots=True)
class ParsedDocument:
    """A document after parsing, before chunking.

    Chunking (Phase 4) consumes `sections`; the naive baseline C0 (Phase 3)
    consumes `text` and ignores the hierarchy entirely. Holding both is what
    lets the two configurations run over identical source material.
    """

    doc_id: str
    title: str
    source_type: SourceType
    category: DocumentCategory
    text: str
    sections: list[Section] = field(default_factory=list)

    # --- Provenance: never optional in spirit, even where typed optional ---
    source_url: str | None = None
    local_path: str | None = None
    fetched_at: str = ""
    content_hash: str = ""

    # --- Descriptive metadata ---
    department: str | None = None
    published_date: str | None = None
    author: str | None = None
    page_count: int | None = None
    language: str = "en"

    # --- Real vs demo ---
    is_demo: bool = False
    demo_reason: str | None = None

    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.fetched_at:
            self.fetched_at = datetime.now(UTC).isoformat()
        if not self.content_hash:
            self.content_hash = compute_content_hash(self.text)

    # --- Invariants -------------------------------------------------------
    def validate(self) -> list[str]:
        """Return a list of problems. Empty list means the document is sound.

        Called by the normaliser before anything is written to disk, so a
        malformed document fails at ingestion rather than surfacing later as a
        citation that points nowhere.
        """
        problems: list[str] = []

        if not self.doc_id:
            problems.append("doc_id is empty")
        if not self.title.strip():
            problems.append("title is empty")
        if not self.text.strip():
            problems.append("text is empty")
        if not self.fetched_at:
            problems.append("fetched_at is empty")
        if not self.content_hash:
            problems.append("content_hash is empty")

        if self.source_url is None and self.local_path is None:
            problems.append("no provenance: both source_url and local_path are None")

        if self.is_demo and not self.demo_reason:
            problems.append("is_demo is True but demo_reason is missing")
        if not self.is_demo and self.category.is_internal_only:
            problems.append(
                f"category '{self.category.value}' is internal-only and cannot be real data; "
                "either mark is_demo=True or re-categorise"
            )

        if (
            self.source_type is SourceType.WEB_PDF
            and self.sections
            and not any(s.start_page is not None for s in self.sections)
        ):
            problems.append("PDF document has no page numbers on any section")

        return problems

    @property
    def file_stem(self) -> str:
        """A filesystem-safe name derived from doc_id.

        doc_id is deliberately allowed to be a real-world identifier such as
        "DEMO/EXAM/2026/03" — that is what a circular number actually looks
        like, and flattening it would make the corpus less faithful. But those
        slashes are path separators, so anything writing a file uses this
        instead. The identifier stays intact in the metadata and the manifest.
        """
        return slugify(self.doc_id.replace("/", "-"))

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def substantive_sections(self) -> list[Section]:
        return [s for s in self.sections if s.is_substantive]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["source_type"] = self.source_type.value
        d["category"] = self.category.value
        return d


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WHITESPACE = re.compile(r"\s+")
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def compute_content_hash(text: str) -> str:
    """Hash the *normalised text*, not the raw bytes.

    A WordPress page whose sidebar advert changed produces different bytes but
    identical extracted text. Hashing the text means a re-crawl only re-ingests
    documents whose content actually changed, which keeps repeat crawls cheap
    and keeps the site's load down.
    """
    normalised = _WHITESPACE.sub(" ", text).strip().lower()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def slugify(value: str, max_length: int = 80) -> str:
    """Lowercase, hyphenated, filesystem-safe."""
    slug = _SLUG_STRIP.sub("-", value.lower()).strip("-")
    if len(slug) > max_length:
        slug = slug[:max_length].rstrip("-")
    return slug or "untitled"
