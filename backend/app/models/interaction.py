"""Users, conversations, citations, verification and evaluation.

Two tables here carry more weight than their size suggests.

`retrieval_logs` records, for every answered question, the rewritten queries,
the dense and sparse candidate lists, the fused ranking, the reranked ranking
and per-stage latency. Every ablation number in Chapter 4 is a query against
this table. Without it, comparing C0 against C5 means re-running both from
scratch and hoping conditions matched; with it, the comparison is a SELECT.

`verification_results` records one row per atomic claim, with the chunk it was
checked against and whether that chunk entailed it. That converts "we reduced
hallucination" from an assertion into a countable rate.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import (
    EntailmentLabel,
    MessageRole,
    PipelineMode,
    QuestionType,
    RunStatus,
    UserRole,
    VerificationStatus,
)
from app.models.mixins import pg_enum, pk


class User(Base, TimestampMixin):
    """Phase 2 uses `admin` only; the other roles exist so enabling them later
    is seed data rather than an enum migration on a populated table."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, "user_role"), nullable=False, default=UserRole.GUEST
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_sessions"
    __table_args__ = (Index("ix_chat_sessions_user", "user_id"),)

    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    title: Mapped[str | None] = mapped_column(String(400))
    mode: Mapped[PipelineMode] = mapped_column(
        pg_enum(PipelineMode, "pipeline_mode"), nullable=False, default=PipelineMode.PROPOSED
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ChatMessage(Base, TimestampMixin):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_session", "session_id"),)

    id: Mapped[uuid.UUID] = pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(pg_enum(MessageRole, "message_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # The LangGraph plan and per-step trace, rendered in the "show reasoning"
    # drawer. This is the explainability feature made durable rather than
    # streamed and forgotten.
    reasoning_trace: Mapped[dict | None] = mapped_column(JSONB)

    latency_ms: Mapped[int | None] = mapped_column(Integer)
    token_count: Mapped[int | None] = mapped_column(Integer)
    model_name: Mapped[str | None] = mapped_column(String(120))
    confidence_score: Mapped[float | None] = mapped_column(Float)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        pg_enum(VerificationStatus, "verification_status"),
        nullable=False,
        default=VerificationStatus.NOT_RUN,
    )

    session: Mapped[ChatSession] = relationship(back_populates="messages")
    citations: Mapped[list[MessageCitation]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


class MessageCitation(Base, TimestampMixin):
    """One `[Sn]` marker resolved to the chunk that supports it.

    `is_demo` is copied from the chunk rather than joined, so the UI badge
    cannot be lost by a query that forgot the join.
    """

    __tablename__ = "message_citations"
    __table_args__ = (
        UniqueConstraint("message_id", "marker", name="uq_citation_message_marker"),
        Index("ix_citations_chunk", "chunk_id"),
    )

    id: Mapped[uuid.UUID] = pk()
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL")
    )
    marker: Mapped[str] = mapped_column(String(16), nullable=False)
    relevance_score: Mapped[float | None] = mapped_column(Float)
    rerank_score: Mapped[float | None] = mapped_column(Float)
    quoted_span: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    message: Mapped[ChatMessage] = relationship(back_populates="citations")


class RetrievalLog(Base, TimestampMixin):
    """Every stage of one retrieval, kept for the ablation study."""

    __tablename__ = "retrieval_logs"
    __table_args__ = (Index("ix_retrieval_logs_message", "message_id"),)

    id: Mapped[uuid.UUID] = pk()
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chat_messages.id", ondelete="CASCADE")
    )
    original_query: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_queries: Mapped[list[str] | None] = mapped_column(JSONB)
    sub_questions: Mapped[list[str] | None] = mapped_column(JSONB)
    dense_hits: Mapped[list | None] = mapped_column(JSONB)
    sparse_hits: Mapped[list | None] = mapped_column(JSONB)
    fused_hits: Mapped[list | None] = mapped_column(JSONB)
    reranked_hits: Mapped[list | None] = mapped_column(JSONB)
    filters_applied: Mapped[dict | None] = mapped_column(JSONB)
    stage_latencies: Mapped[dict | None] = mapped_column(JSONB)
    iteration_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    config_name: Mapped[str | None] = mapped_column(String(32))


class VerificationResult(Base, TimestampMixin):
    """One atomic claim, checked against the chunk that was cited for it."""

    __tablename__ = "verification_results"
    __table_args__ = (Index("ix_verification_message", "message_id"),)

    id: Mapped[uuid.UUID] = pk()
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False
    )
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL")
    )
    entailment_label: Mapped[EntailmentLabel] = mapped_column(
        pg_enum(EntailmentLabel, "entailment_label"), nullable=False
    )
    entailment_score: Mapped[float | None] = mapped_column(Float)
    action_taken: Mapped[str | None] = mapped_column(String(64))


class Feedback(Base, TimestampMixin):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = pk()
    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    rating: Mapped[int | None] = mapped_column(SmallInteger)
    was_helpful: Mapped[bool | None] = mapped_column(Boolean)
    comment: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


class EvalDataset(Base, TimestampMixin):
    __tablename__ = "eval_datasets"

    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    questions: Mapped[list[EvalQuestion]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )


class EvalQuestion(Base, TimestampMixin):
    """A golden-set question.

    `UNANSWERABLE` questions are deliberate: a system that answers a question
    the corpus cannot support is hallucinating, and refusal is the correct
    behaviour. Around 10% of the set is this type, so refusal is measured
    rather than assumed.
    """

    __tablename__ = "eval_questions"
    __table_args__ = (Index("ix_eval_questions_dataset", "dataset_id"),)

    id: Mapped[uuid.UUID] = pk()
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("eval_datasets.id", ondelete="CASCADE"), nullable=False
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    ground_truth: Mapped[str | None] = mapped_column(Text)
    question_type: Mapped[QuestionType] = mapped_column(
        pg_enum(QuestionType, "question_type"), nullable=False, default=QuestionType.FACTUAL
    )
    expected_doc_ids: Mapped[list[str] | None] = mapped_column(JSONB)
    difficulty: Mapped[int | None] = mapped_column(SmallInteger)

    dataset: Mapped[EvalDataset] = relationship(back_populates="questions")


class EvalRun(Base, TimestampMixin):
    """One execution of one configuration over one dataset."""

    __tablename__ = "eval_runs"
    __table_args__ = (Index("ix_eval_runs_dataset", "dataset_id"),)

    id: Mapped[uuid.UUID] = pk()
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("eval_datasets.id", ondelete="CASCADE"), nullable=False
    )
    config_name: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict | None] = mapped_column(JSONB)
    model_name: Mapped[str | None] = mapped_column(String(120))
    judge_model_name: Mapped[str | None] = mapped_column(String(120))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[RunStatus] = mapped_column(
        pg_enum(RunStatus, "run_status"), nullable=False, default=RunStatus.QUEUED
    )

    results: Mapped[list[EvalResult]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class EvalResult(Base, TimestampMixin):
    __tablename__ = "eval_results"
    __table_args__ = (
        UniqueConstraint("run_id", "question_id", name="uq_eval_result_run_question"),
    )

    id: Mapped[uuid.UUID] = pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("eval_questions.id", ondelete="CASCADE"), nullable=False
    )
    generated_answer: Mapped[str | None] = mapped_column(Text)
    retrieved_context: Mapped[list | None] = mapped_column(JSONB)

    faithfulness: Mapped[float | None] = mapped_column(Float)
    answer_relevancy: Mapped[float | None] = mapped_column(Float)
    context_precision: Mapped[float | None] = mapped_column(Float)
    context_recall: Mapped[float | None] = mapped_column(Float)

    judge_score: Mapped[float | None] = mapped_column(Float)
    judge_rationale: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    refused: Mapped[bool | None] = mapped_column(Boolean)

    run: Mapped[EvalRun] = relationship(back_populates="results")


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


class IngestionJob(Base, TimestampMixin):
    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = pk()
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str | None] = mapped_column(Text)
    status: Mapped[RunStatus] = mapped_column(
        pg_enum(RunStatus, "run_status"), nullable=False, default=RunStatus.QUEUED
    )
    documents_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    documents_suppressed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunks_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    log: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_created_at", "created_at"),)

    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(120))
    entity_id: Mapped[str | None] = mapped_column(String(200))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict | None] = mapped_column(JSONB)


__all__ = [
    "AuditLog",
    "ChatMessage",
    "ChatSession",
    "EvalDataset",
    "EvalQuestion",
    "EvalResult",
    "EvalRun",
    "Feedback",
    "IngestionJob",
    "MessageCitation",
    "RetrievalLog",
    "User",
    "VerificationResult",
]
