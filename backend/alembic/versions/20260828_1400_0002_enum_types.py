"""Create the native enum types the schema depends on.

Separated from the table DDL on purpose. Several enums are used by more than
one table — `run_status` by both `eval_runs` and `ingestion_jobs` — and if
SQLAlchemy owned their creation it would try to emit CREATE TYPE once per
table and fail on the second. Every Enum in the models therefore sets
`create_type=False`, and this revision is the single place the types are
created and dropped.

Adding a new enum, or a new member to an existing one, means editing this file
and writing an ALTER TYPE in a later revision. That friction is deliberate:
these values appear in API responses and in the corpus manifest, so changing
one is a schema change rather than a rename.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_enum_types"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# name -> values, mirroring app/models/enums.py exactly.
ENUM_TYPES: dict[str, tuple[str, ...]] = {
    "program_level": ("btech", "mtech", "phd", "diploma", "certificate"),
    "announcement_category": (
        "notice",
        "circular",
        "result",
        "admission",
        "event",
        "examination",
        "general",
    ),
    "facility_category": ("lab", "library", "sports", "hostel", "infrastructure", "other"),
    "accreditation_body": ("naac", "nba", "nirf", "ariia", "ugc", "aicte", "other"),
    "source_type": ("web_html", "web_pdf", "local_markdown", "manual_entry"),
    "document_category": (
        "institute_profile",
        "accreditation",
        "programme",
        "curriculum",
        "department",
        "faculty",
        "research",
        "library",
        "student_life",
        "placement",
        "admission",
        "announcement",
        "event",
        "report",
        "governance",
        "contact",
        "alumni",
        "internal_wiki",
        "sop",
        "circular",
        "lab_manual",
        "helpdesk",
        "timetable",
        "other",
    ),
    "ingest_status": ("pending", "parsed", "chunked", "indexed", "failed"),
    "user_role": ("guest", "student", "faculty", "admin"),
    "pipeline_mode": ("baseline", "proposed"),
    "message_role": ("user", "assistant", "system"),
    "verification_status": ("verified", "partial", "unverified", "not_run"),
    "entailment_label": ("supported", "contradicted", "not_found"),
    "question_type": ("factual", "multi_hop", "comparative", "temporal", "unanswerable"),
    "run_status": ("queued", "running", "succeeded", "failed", "cancelled"),
}


def upgrade() -> None:
    for name, values in ENUM_TYPES.items():
        members = ", ".join(f"'{value}'" for value in values)
        # DO block rather than CREATE TYPE IF NOT EXISTS, which PostgreSQL does
        # not support for types.
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{name}') THEN
                    CREATE TYPE {name} AS ENUM ({members});
                END IF;
            END
            $$;
            """
        )


def downgrade() -> None:
    # Reverse order so a type is never dropped while a later one still
    # references it. (None do today, but the ordering costs nothing.)
    for name in reversed(list(ENUM_TYPES)):
        op.execute(f"DROP TYPE IF EXISTS {name};")
