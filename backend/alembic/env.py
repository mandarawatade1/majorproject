"""Alembic environment.

The database URL comes from app.core.config (which reads .env), never from
alembic.ini, so credentials live in exactly one place.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import engine_from_config, pool

from alembic import context

# Make the `app` package importable when alembic runs from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)

# Autogenerate compares the live database against this metadata.
target_metadata = Base.metadata


def render_item(type_: str, obj: object, autogen_context: object) -> str | bool:
    """Render enum columns as postgresql.ENUM(..., create_type=False).

    Enum types are created once, by revision 0002_enum_types, and never by the
    table DDL. Two independent reasons:

    1. Six of the fourteen are shared between tables — `run_status` by both
       `eval_runs` and `ingestion_jobs`. If each CREATE TABLE owned its type,
       the second table would fail with DuplicateObject even on a database
       where nothing had created it before.
    2. The models already set create_type=False, so nothing else emits the DDL.

    The hook is necessary because autogenerate does NOT carry create_type
    across from the model: it re-renders a type from its name and values alone.
    Without this, every generated migration silently reintroduces
    `sa.Enum(...)` with type creation switched on, and `alembic upgrade head`
    fails on a completely fresh database.
    """
    if type_ == "type" and isinstance(obj, sa.Enum):
        autogen_context.imports.add("from sqlalchemy.dialects import postgresql")
        values = ", ".join(repr(value) for value in obj.enums)
        return f"postgresql.ENUM({values}, name={obj.name!r}, create_type=False)"
    return False


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (alembic upgrade head --sql)."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and apply migrations."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_item=render_item,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
