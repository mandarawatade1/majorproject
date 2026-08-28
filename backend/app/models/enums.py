"""Enumerations shared across the schema.

These are declared as native PostgreSQL enum types rather than free-text
columns, so the database refuses a value the application never intended. That
matters most for `UserRole` and for the demo/real distinction downstream: a
constraint the database enforces cannot be forgotten by a future code path.

The string values are lowercase and stable. They appear in API responses and in
the manifest, so renaming one is a migration, not a refactor.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Four roles from the first migration, even though Phase 2 only uses two.

    The approved scope is a public portal plus an admin console. Declaring
    `student` and `faculty` now means switching on full RBAC later is route
    guards and seed data rather than an enum migration on a populated table.
    """

    GUEST = "guest"
    STUDENT = "student"
    FACULTY = "faculty"
    ADMIN = "admin"


class ProgramLevel(StrEnum):
    BTECH = "btech"
    MTECH = "mtech"
    PHD = "phd"
    DIPLOMA = "diploma"
    CERTIFICATE = "certificate"


class AnnouncementCategory(StrEnum):
    NOTICE = "notice"
    CIRCULAR = "circular"
    RESULT = "result"
    ADMISSION = "admission"
    EVENT = "event"
    EXAMINATION = "examination"
    GENERAL = "general"


class FacilityCategory(StrEnum):
    LAB = "lab"
    LIBRARY = "library"
    SPORTS = "sports"
    HOSTEL = "hostel"
    INFRASTRUCTURE = "infrastructure"
    OTHER = "other"


class AccreditationBody(StrEnum):
    NAAC = "naac"
    NBA = "nba"
    NIRF = "nirf"
    ARIIA = "ariia"
    UGC = "ugc"
    AICTE = "aicte"
    OTHER = "other"


class SourceType(StrEnum):
    """Mirrors rag.ingestion.models.SourceType.

    Deliberately duplicated rather than imported. The knowledge service must not
    depend on the API layer, and the API's persisted schema must not shift
    because a pipeline enum was renamed. The seed loader maps between them
    explicitly, and a test asserts the two stay in step.
    """

    WEB_HTML = "web_html"
    WEB_PDF = "web_pdf"
    LOCAL_MARKDOWN = "local_markdown"
    MANUAL_ENTRY = "manual_entry"


class DocumentCategory(StrEnum):
    """Mirrors rag.ingestion.models.DocumentCategory, plus MANUAL."""

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
    INTERNAL_WIKI = "internal_wiki"
    SOP = "sop"
    CIRCULAR = "circular"
    LAB_MANUAL = "lab_manual"
    HELPDESK = "helpdesk"
    TIMETABLE = "timetable"
    OTHER = "other"


class IngestStatus(StrEnum):
    PENDING = "pending"
    PARSED = "parsed"
    CHUNKED = "chunked"
    INDEXED = "indexed"
    FAILED = "failed"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class PipelineMode(StrEnum):
    """Which configuration answered a question.

    Persisted per chat session so the C0-C5 comparison in Chapter 4 can be run
    against real user traffic, not only against the golden set.
    """

    BASELINE = "baseline"
    PROPOSED = "proposed"


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    PARTIAL = "partial"
    UNVERIFIED = "unverified"
    NOT_RUN = "not_run"


class EntailmentLabel(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    NOT_FOUND = "not_found"


class QuestionType(StrEnum):
    FACTUAL = "factual"
    MULTI_HOP = "multi_hop"
    COMPARATIVE = "comparative"
    TEMPORAL = "temporal"
    UNANSWERABLE = "unanswerable"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


__all__ = [
    "AccreditationBody",
    "AnnouncementCategory",
    "DocumentCategory",
    "EntailmentLabel",
    "FacilityCategory",
    "IngestStatus",
    "MessageRole",
    "PipelineMode",
    "ProgramLevel",
    "QuestionType",
    "RunStatus",
    "SourceType",
    "UserRole",
    "VerificationStatus",
]
