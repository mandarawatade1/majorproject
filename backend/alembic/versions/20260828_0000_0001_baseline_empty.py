"""Baseline: establish the migration chain.

Deliberately empty. Running `alembic upgrade head` against a fresh database
creates the alembic_version table and stamps it at this revision, which is what
makes Phase 0 verifiable: the migration machinery is proven to work before any
real schema exists.

Phase 2 adds the schema from Docs/architecture-plan.md section 4 on top of
this revision.
"""

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
