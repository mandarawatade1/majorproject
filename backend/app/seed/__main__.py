"""Seed the database.

    docker compose exec api python -m app.seed              # everything
    docker compose exec api python -m app.seed reference    # departments etc.
    docker compose exec api python -m app.seed corpus       # the Phase 1 corpus
    docker compose exec api python -m app.seed admin        # the admin account

Every step is idempotent: running it twice is the same as running it once.
That matters because the seed is what a supervisor runs on a clean machine
during a demo, and a seed that only works on an empty database is a seed that
fails at exactly the wrong moment.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.session import SessionLocal
from app.models.enums import AccreditationBody, ProgramLevel, UserRole
from app.models.institutional import Accreditation, Department, Program
from app.models.interaction import User
from app.seed.corpus import load_corpus
from app.seed.reference import (
    ACCREDITATIONS,
    BTECH_PROGRAMS,
    DEPARTMENTS,
    TOTAL_BTECH_INTAKE,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------


def seed_reference(session: Session) -> None:
    """Departments, B.Tech programmes and accreditation, from public sources."""
    by_code: dict[str, Department] = {d.code: d for d in session.scalars(select(Department))}

    for row in DEPARTMENTS:
        department = by_code.get(row["code"])
        if department is None:
            department = Department(**row)
            session.add(department)
            by_code[row["code"]] = department
        else:
            for key, value in row.items():
                setattr(department, key, value)
    session.flush()

    # A typo in one intake would otherwise pass unnoticed until someone asked
    # the assistant for the total.
    total = sum(p["intake"] for p in BTECH_PROGRAMS)
    if total != TOTAL_BTECH_INTAKE:
        raise ValueError(
            f"B.Tech intakes sum to {total}, but the bachelors page states "
            f"{TOTAL_BTECH_INTAKE}. Fix app/seed/reference.py before seeding."
        )

    existing_programs = {(p.slug): p for p in session.scalars(select(Program))}
    for row in BTECH_PROGRAMS:
        data = dict(row)
        department = by_code[data.pop("department_code")]
        program = existing_programs.get(data["slug"])
        if program is None:
            session.add(
                Program(
                    department_id=department.id,
                    level=ProgramLevel.BTECH,
                    duration_years=4,
                    source_url="https://www.pce.ac.in/academics/bachelors/",
                    **data,
                )
            )
        else:
            program.department_id = department.id
            for key, value in data.items():
                setattr(program, key, value)

    existing_bodies = {a.body for a in session.scalars(select(Accreditation))}
    for row in ACCREDITATIONS:
        body = AccreditationBody(row["body"])
        if body in existing_bodies:
            continue
        session.add(Accreditation(**{**row, "body": body}))

    session.flush()
    logger.info(
        "seed_reference",
        departments=len(DEPARTMENTS),
        programs=len(BTECH_PROGRAMS),
        total_intake=total,
    )


def seed_admin(session: Session) -> None:
    """Create the admin account, if the configured email is not already taken."""
    from passlib.context import CryptContext

    email = settings.admin_email
    password = settings.admin_password

    if not password or password.startswith("change_this"):
        logger.warning(
            "seed_admin_skipped",
            reason="ADMIN_PASSWORD is unset or still the placeholder in .env",
        )
        return

    if session.scalar(select(User).where(User.email == email)) is not None:
        logger.info("seed_admin", status="already exists", email=email)
        return

    context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    session.add(
        User(
            email=email,
            password_hash=context.hash(password),
            full_name="Administrator",
            role=UserRole.ADMIN,
            is_active=True,
        )
    )
    session.flush()
    logger.info("seed_admin", status="created", email=email)


def seed_corpus(session: Session) -> None:
    corpus_dir = Path(settings.corpus_dir)
    report = load_corpus(session, corpus_dir)
    print(report.summary())
    if report.skipped:
        print(f"\n{len(report.skipped)} document(s) skipped:")
        for line in report.skipped[:15]:
            print(f"  {line}")


def verify(session: Session) -> int:
    """Print what is actually in the database. Run after any seed step."""
    from app.models.knowledge import Document, DocumentSection

    counts = {
        "departments": session.scalar(select(func.count()).select_from(Department)),
        "programs": session.scalar(select(func.count()).select_from(Program)),
        "accreditations": session.scalar(select(func.count()).select_from(Accreditation)),
        "documents": session.scalar(select(func.count()).select_from(Document)),
        "document_sections": session.scalar(select(func.count()).select_from(DocumentSection)),
        "users": session.scalar(select(func.count()).select_from(User)),
    }
    real = session.scalar(select(func.count()).select_from(Document).where(~Document.is_demo))
    demo = session.scalar(select(func.count()).select_from(Document).where(Document.is_demo))
    with_pages = session.scalar(
        select(func.count(func.distinct(DocumentSection.document_id))).where(
            DocumentSection.start_page.isnot(None)
        )
    )

    print("\nDatabase contents")
    print("=" * 40)
    width = max(len(k) for k in counts)
    for key, value in counts.items():
        print(f"  {key:<{width}}  {value}")

    total = (real or 0) + (demo or 0)
    if total:
        print(f"\n  real documents      {real}  ({(real or 0) / total:.1%})")
        print(f"  demo documents      {demo}")
        print(f"  with page numbers   {with_pages}")

    return 0


# ---------------------------------------------------------------------------


STEPS = {
    "reference": seed_reference,
    "corpus": seed_corpus,
    "admin": seed_admin,
}


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="python -m app.seed")
    parser.add_argument(
        "steps",
        nargs="*",
        choices=[*STEPS, "all"],
        default=["all"],
        help="Which steps to run. Default: all.",
    )
    args = parser.parse_args(argv)

    chosen = list(STEPS) if "all" in args.steps or not args.steps else args.steps

    with SessionLocal() as session:
        try:
            for name in chosen:
                print(f"==> {name}")
                STEPS[name](session)
            session.commit()
        except Exception as exc:
            session.rollback()
            print(f"\nSEED FAILED during '{name}': {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1

        return verify(session)


if __name__ == "__main__":
    raise SystemExit(main())
