"""Declarative base and the model registry Alembic reads.

Alembic's autogenerate walks Base.metadata. A model class that is never
imported into this module is invisible to it, and its table will silently
never be created. Phase 2 adds those imports at the bottom of this file.
"""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for every ORM model in the project."""


class TimestampMixin:
    """created_at / updated_at, maintained by the database rather than Python."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Model registration.
#
# Alembic's autogenerate walks Base.metadata, which is populated as a
# side effect of importing the model modules. The import sits at the BOTTOM of
# this file because the models import Base from here — putting it at the top
# would be circular.
#
# A model module missing from this list is invisible to migrations, and its
# table will silently never be created.
# ---------------------------------------------------------------------------
from app.models import institutional, interaction, knowledge  # noqa: E402,F401

__all__ = ["Base", "TimestampMixin"]
