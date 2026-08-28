"""Schema tests.

The unit tests here need no database. The integration tests need a live
PostgreSQL and are what CI runs; they are the safety net for a schema whose
migration was generated rather than hand-written.

The drift check is the important one. It applies every migration to an empty
database and then asks Alembic to diff the result against `Base.metadata`. Any
difference — a column the migration missed, a type that does not match, an
index declared on the model but never created — fails the build. Without it,
a model change merged without its migration would only surface when a query
hit a column that does not exist in production.
"""

from __future__ import annotations

import os

import pytest

from app.db.base import Base
from app.models import enums


class TestMetadataShape:
    """Structural assertions that need no database connection."""

    def test_every_model_module_is_registered(self) -> None:
        """A model missing from app.db.base is invisible to Alembic."""
        tables = set(Base.metadata.tables)
        for expected in ("departments", "documents", "chunks", "users", "eval_runs"):
            assert expected in tables, f"{expected} missing — is its module imported in db.base?"

    def test_table_count_is_what_the_plan_describes(self) -> None:
        assert len(Base.metadata.tables) == 27

    def test_every_table_has_a_primary_key(self) -> None:
        missing = [n for n, t in Base.metadata.tables.items() if not t.primary_key.columns]
        assert missing == []

    def test_every_table_has_timestamps(self) -> None:
        missing = [
            name
            for name, table in Base.metadata.tables.items()
            if "created_at" not in table.columns or "updated_at" not in table.columns
        ]
        assert missing == []


class TestDemoFlagPropagation:
    """The real-versus-demo guarantee, enforced by the schema.

    Phase 1 made `is_demo` a property of every parsed document. These tests
    check the promise survives into the database: the tables that can carry
    institutional fact all have the column, it is never nullable, and the two
    tables that a citation is built from carry it directly so the badge cannot
    be lost by a query that forgot a join.
    """

    CARRYING_TABLES = (
        "departments",
        "programs",
        "courses",
        "faculty",
        "announcements",
        "events",
        "facilities",
        "placements",
        "accreditations",
        "contacts",
        "documents",
        "chunks",
    )

    @pytest.mark.parametrize("table_name", CARRYING_TABLES)
    def test_table_carries_is_demo(self, table_name: str) -> None:
        table = Base.metadata.tables[table_name]
        assert "is_demo" in table.columns, f"{table_name} cannot distinguish real from demo data"

    @pytest.mark.parametrize("table_name", CARRYING_TABLES)
    def test_is_demo_is_never_nullable(self, table_name: str) -> None:
        """A row that is neither real nor demo must be impossible."""
        assert Base.metadata.tables[table_name].columns["is_demo"].nullable is False

    def test_citations_carry_the_flag_without_a_join(self) -> None:
        assert "is_demo" in Base.metadata.tables["message_citations"].columns

    def test_chunks_carry_page_provenance(self) -> None:
        """Page-level provenance is a project requirement, so the column that
        makes it possible is asserted rather than assumed."""
        columns = Base.metadata.tables["chunks"].columns
        assert "page_number" in columns
        assert "section_path" in columns


class TestProvenanceConstraint:
    def test_documents_require_a_location(self) -> None:
        """A document traceable to nowhere must not be insertable."""
        constraints = {c.name for c in Base.metadata.tables["documents"].constraints}
        assert "ck_documents_has_provenance" in constraints

    def test_documents_require_a_content_hash(self) -> None:
        assert Base.metadata.tables["documents"].columns["content_hash"].nullable is False


class TestEnumsMatchThePipeline:
    """The API's enums deliberately duplicate the pipeline's rather than
    importing them, so the knowledge service stays free of any dependency on
    the API. Duplication without a test is how two copies drift apart."""

    def test_document_categories_are_a_superset_of_the_pipeline_s(self) -> None:
        from rag.ingestion.models import DocumentCategory as PipelineCategory

        api = {member.value for member in enums.DocumentCategory}
        pipeline = {member.value for member in PipelineCategory}
        assert pipeline <= api, f"pipeline categories missing from the API enum: {pipeline - api}"

    def test_source_types_are_a_superset_of_the_pipeline_s(self) -> None:
        from rag.ingestion.models import SourceType as PipelineSourceType

        api = {member.value for member in enums.SourceType}
        pipeline = {member.value for member in PipelineSourceType}
        assert pipeline <= api, f"pipeline source types missing from the API enum: {pipeline - api}"

    def test_the_migration_declares_every_enum_the_models_use(self) -> None:
        """The enum types are created by hand in 0002. If a model gains an enum
        and that file is not updated, the table DDL will reference a type that
        does not exist."""
        import importlib.util
        from pathlib import Path

        path = next(Path(__file__).resolve().parents[1].glob("alembic/versions/*_enum_types.py"))
        spec = importlib.util.spec_from_file_location("enum_types_migration", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        declared = set(module.ENUM_TYPES)
        used = {
            column.type.name
            for table in Base.metadata.tables.values()
            for column in table.columns
            if getattr(column.type, "name", None) and hasattr(column.type, "enums")
        }
        assert used <= declared, f"enum types used by models but not created: {used - declared}"

    def test_declared_enum_members_match_the_python_enums(self) -> None:
        import importlib.util
        from pathlib import Path

        path = next(Path(__file__).resolve().parents[1].glob("alembic/versions/*_enum_types.py"))
        spec = importlib.util.spec_from_file_location("enum_types_migration", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        for table in Base.metadata.tables.values():
            for column in table.columns:
                name = getattr(column.type, "name", None)
                if not name or name not in module.ENUM_TYPES:
                    continue
                assert set(column.type.enums) == set(module.ENUM_TYPES[name]), (
                    f"enum '{name}' differs between the models and migration 0002"
                )


class TestMigrationsNeverCreateEnumTypes:
    """No migration may create an enum type as a side effect of CREATE TABLE.

    Enum types are owned by revision 0002_enum_types. Two reasons this must be
    enforced rather than remembered:

    1. Six of the fourteen types are shared between tables — `run_status` by
       both `eval_runs` and `ingestion_jobs`. A CREATE TABLE that owns its type
       fails on the second table with DuplicateObject, even on a database where
       nothing had created it before.
    2. Alembic's autogenerate does NOT carry `create_type=False` across from
       the model. It re-renders a type from its name and values alone, so every
       regenerated migration reintroduces the fault unless `render_item` in
       alembic/env.py rewrites it.

    This exact defect broke `alembic upgrade head` on a completely fresh
    database. The test needs no database, so it fails in seconds rather than
    after a container build.
    """

    @staticmethod
    def _migration_sources() -> list[tuple[str, str]]:
        from pathlib import Path

        versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
        return [(p.name, p.read_text(encoding="utf-8")) for p in sorted(versions.glob("*.py"))]

    def test_no_migration_uses_bare_sa_enum(self) -> None:
        offenders = [name for name, src in self._migration_sources() if "sa.Enum(" in src]
        assert offenders == [], (
            f"{offenders} use sa.Enum(), which creates the type during CREATE TABLE. "
            "Use postgresql.ENUM(..., create_type=False); alembic/env.py's render_item "
            "hook does this automatically for newly generated migrations."
        )

    def test_every_enum_column_disables_type_creation(self) -> None:
        import re

        offenders: list[str] = []
        for name, src in self._migration_sources():
            for match in re.finditer(r"postgresql\.ENUM\((?:[^()]*)\)", src):
                if "create_type=False" not in match.group(0):
                    offenders.append(f"{name}: {match.group(0)[:70]}...")
        assert offenders == [], f"enum columns that would create their type: {offenders}"

    def test_the_env_hook_that_keeps_this_true_is_present(self) -> None:
        """Without render_item, the next autogenerate silently undoes the fix."""
        from pathlib import Path

        env = (Path(__file__).resolve().parents[1] / "alembic" / "env.py").read_text()
        assert "render_item" in env, (
            "alembic/env.py has lost its render_item hook. The next "
            "`alembic revision --autogenerate` will emit sa.Enum(...) again and "
            "`alembic upgrade head` will fail on a fresh database."
        )
        assert "create_type=False" in env


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("POSTGRES_HOST"), reason="needs a live PostgreSQL")
class TestMigrationsAgainstADatabase:
    """The safety net for a migration that was generated rather than reviewed
    line by line."""

    def test_migrations_leave_no_drift_against_the_models(self) -> None:
        """Apply every migration, then diff the result against Base.metadata.

        An empty diff means the migration and the models agree. A non-empty one
        names exactly what is missing.
        """
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext

        from app.db.session import engine

        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={"compare_type": True, "compare_server_default": True},
            )
            diff = compare_metadata(context, Base.metadata)

        # Alembic reports enum types it did not create as removals; they are
        # created by hand in 0002, so ignore that one category.
        meaningful = [entry for entry in diff if "remove_type" not in str(entry[0])]
        assert meaningful == [], f"schema drift between migrations and models: {meaningful}"

    def test_every_table_exists(self) -> None:
        from sqlalchemy import inspect

        from app.db.session import engine

        actual = set(inspect(engine).get_table_names())
        expected = set(Base.metadata.tables)
        assert expected <= actual, f"tables missing from the database: {expected - actual}"
