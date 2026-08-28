"""SQLAlchemy ORM models.

Grouped by domain, matching Docs/architecture-plan.md section 4:

    institutional.py  the tables behind the portal pages
    knowledge.py      documents, sections, chunks — the corpus
    interaction.py    users, chats, citations, verification, evaluation

Every model must also be imported into app.db.base, which is what Alembic's
autogenerate walks. A model missing from there is invisible to migrations and
its table will silently never be created.
"""

from app.models.institutional import (
    Accreditation,
    Announcement,
    Contact,
    Course,
    Department,
    Event,
    Facility,
    Faculty,
    Placement,
    Program,
)
from app.models.interaction import (
    AuditLog,
    ChatMessage,
    ChatSession,
    EvalDataset,
    EvalQuestion,
    EvalResult,
    EvalRun,
    Feedback,
    IngestionJob,
    MessageCitation,
    RetrievalLog,
    User,
    VerificationResult,
)
from app.models.knowledge import Chunk, Document, DocumentSection, SuppressedDocument

__all__ = [
    "Accreditation",
    "Announcement",
    "AuditLog",
    "ChatMessage",
    "ChatSession",
    "Chunk",
    "Contact",
    "Course",
    "Department",
    "Document",
    "DocumentSection",
    "EvalDataset",
    "EvalQuestion",
    "EvalResult",
    "EvalRun",
    "Event",
    "Facility",
    "Faculty",
    "Feedback",
    "IngestionJob",
    "MessageCitation",
    "Placement",
    "Program",
    "RetrievalLog",
    "SuppressedDocument",
    "User",
    "VerificationResult",
]
