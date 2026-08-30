"""Public portal read endpoints.

Everything here is read-only and unauthenticated by design: this is the part of
the site a prospective student browses. Writes, ingestion and the evaluation
console are admin surface and belong to a later phase.

One rule runs through every response in this file: **`is_demo` is always
present, never filtered out silently.** The corpus is deliberately part real
and part synthetic, and a portal that showed the two identically would be
misleading in exactly the way the project set out not to be. Each endpoint
accepts `include_demo` so a caller can ask for real records only, and every
record says which it is.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from app.db.session import get_db
from app.models.institutional import (
    Announcement,
    Department,
    Event,
    Facility,
    Faculty,
    Program,
)
from app.models.knowledge import Document
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

router = APIRouter(tags=["portal"])

DbSession = Annotated[Session, Depends(get_db)]

MAX_PAGE_SIZE = 100


def _demo_filter(statement: Any, model: Any, include_demo: bool) -> Any:
    return statement if include_demo else statement.where(model.is_demo.is_(False))


def _page(db: Session, statement: Any, limit: int, offset: int) -> dict[str, Any]:
    """A page of rows plus the total, so a client can paginate honestly.

    The count is a separate query against the same filters rather than
    `len(rows)`, which would report the page size and make "showing 20 of 20"
    true of every page.
    """
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    rows = db.scalars(statement.limit(limit).offset(offset)).all()
    return {"total": total or 0, "limit": limit, "offset": offset, "items": rows}


# ---------------------------------------------------------------------------
# Departments and programmes
# ---------------------------------------------------------------------------


@router.get("/departments", summary="All departments")
def list_departments(
    db: DbSession,
    include_demo: bool = Query(True, description="Include synthetic records"),
) -> dict[str, Any]:
    statement = _demo_filter(select(Department).order_by(Department.name), Department, include_demo)
    rows = db.scalars(statement).all()
    return {
        "total": len(rows),
        "items": [
            {
                "id": str(d.id),
                "code": d.code,
                "name": d.name,
                "slug": d.slug,
                "established_year": d.established_year,
                "hod_name": d.hod_name,
                "about": d.about,
                "email": d.email,
                "source_url": d.source_url,
                "is_demo": d.is_demo,
            }
            for d in rows
        ],
    }


@router.get("/departments/{slug}", summary="One department, with its programmes")
def get_department(slug: str, db: DbSession) -> dict[str, Any]:
    department = db.scalar(select(Department).where(Department.slug == slug))
    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no department with slug {slug!r}",
        )

    programs = db.scalars(
        select(Program)
        .where(Program.department_id == department.id)
        .order_by(Program.level, Program.name)
    ).all()
    faculty_count = db.scalar(
        select(func.count()).select_from(Faculty).where(Faculty.department_id == department.id)
    )

    return {
        "id": str(department.id),
        "code": department.code,
        "name": department.name,
        "slug": department.slug,
        "established_year": department.established_year,
        "hod_name": department.hod_name,
        "about": department.about,
        "vision": department.vision,
        "mission": department.mission,
        "email": department.email,
        "phone": department.phone,
        "source_url": department.source_url,
        "is_demo": department.is_demo,
        "faculty_count": faculty_count or 0,
        "programs": [
            {
                "id": str(p.id),
                "name": p.name,
                "slug": p.slug,
                "level": p.level.value,
                "intake": p.intake,
                "duration_years": p.duration_years,
                "curriculum_url": p.curriculum_url,
                "is_demo": p.is_demo,
            }
            for p in programs
        ],
    }


@router.get("/programs", summary="All programmes")
def list_programs(
    db: DbSession,
    level: str | None = Query(None, description="Filter by programme level"),
    include_demo: bool = Query(True),
) -> dict[str, Any]:
    statement = select(Program).order_by(Program.level, Program.name)
    if level:
        statement = statement.where(Program.level == level.lower())
    statement = _demo_filter(statement, Program, include_demo)

    rows = db.scalars(statement).all()
    return {
        "total": len(rows),
        "items": [
            {
                "id": str(p.id),
                "name": p.name,
                "slug": p.slug,
                "level": p.level.value,
                "department_id": str(p.department_id) if p.department_id else None,
                "intake": p.intake,
                "duration_years": p.duration_years,
                "description": p.description,
                "curriculum_url": p.curriculum_url,
                "source_url": p.source_url,
                "is_demo": p.is_demo,
            }
            for p in rows
        ],
    }


# ---------------------------------------------------------------------------
# People, notices, facilities
# ---------------------------------------------------------------------------


@router.get("/faculty", summary="Faculty directory")
def list_faculty(
    db: DbSession,
    department: str | None = Query(None, description="Department slug"),
    limit: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    include_demo: bool = Query(True),
) -> dict[str, Any]:
    statement = select(Faculty).order_by(Faculty.name)
    if department:
        dept = db.scalar(select(Department).where(Department.slug == department))
        if dept is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"no department with slug {department!r}",
            )
        statement = statement.where(Faculty.department_id == dept.id)
    statement = _demo_filter(statement, Faculty, include_demo)

    page = _page(db, statement, limit, offset)
    page["items"] = [
        {
            "id": str(f.id),
            "name": f.name,
            "designation": f.designation,
            "qualification": f.qualification,
            "specialisation": f.specialisation,
            "email": f.email,
            "experience_years": f.experience_years,
            "profile_url": f.profile_url,
            "department_id": str(f.department_id) if f.department_id else None,
            "is_demo": f.is_demo,
        }
        for f in page["items"]
    ]
    return page


@router.get("/announcements", summary="Notices, most recent first")
def list_announcements(
    db: DbSession,
    category: str | None = Query(None),
    limit: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    include_demo: bool = Query(True),
) -> dict[str, Any]:
    statement = select(Announcement).order_by(
        Announcement.priority.desc(), Announcement.published_at.desc().nullslast()
    )
    if category:
        statement = statement.where(Announcement.category == category.lower())
    statement = _demo_filter(statement, Announcement, include_demo)

    page = _page(db, statement, limit, offset)
    page["items"] = [
        {
            "id": str(a.id),
            "title": a.title,
            "body": a.body,
            "category": a.category.value,
            "published_at": a.published_at.isoformat() if a.published_at else None,
            "priority": a.priority,
            "attachment_url": a.attachment_url,
            "source_url": a.source_url,
            "is_demo": a.is_demo,
        }
        for a in page["items"]
    ]
    return page


@router.get("/events", summary="Events, soonest first")
def list_events(
    db: DbSession,
    limit: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    include_demo: bool = Query(True),
) -> dict[str, Any]:
    statement = _demo_filter(
        select(Event).order_by(Event.starts_at.desc().nullslast()),
        Event,
        include_demo,
    )
    page = _page(db, statement, limit, offset)
    page["items"] = [
        {
            "id": str(e.id),
            "title": e.title,
            "description": e.description,
            "starts_at": e.starts_at.isoformat() if e.starts_at else None,
            "venue": e.venue,
            "organiser": e.organiser,
            "source_url": e.source_url,
            "is_demo": e.is_demo,
        }
        for e in page["items"]
    ]
    return page


@router.get("/facilities", summary="Laboratories and other facilities")
def list_facilities(db: DbSession, include_demo: bool = Query(True)) -> dict[str, Any]:
    statement = _demo_filter(select(Facility).order_by(Facility.name), Facility, include_demo)
    rows = db.scalars(statement).all()
    return {
        "total": len(rows),
        "items": [
            {
                "id": str(f.id),
                "name": f.name,
                "category": f.category.value,
                "description": f.description,
                "department_id": str(f.department_id) if f.department_id else None,
                "source_url": f.source_url,
                "is_demo": f.is_demo,
            }
            for f in rows
        ],
    }


# ---------------------------------------------------------------------------
# The corpus itself
# ---------------------------------------------------------------------------


@router.get("/corpus/stats", summary="What the assistant actually knows")
def corpus_stats(db: DbSession) -> dict[str, Any]:
    """The real/demo split, served rather than asserted.

    The project claims a corpus that is roughly 80% real institutional content.
    Publishing the counts lets a visitor — or an examiner — check the claim
    instead of taking it on trust.
    """
    total = db.scalar(select(func.count()).select_from(Document)) or 0
    demo = (
        db.scalar(select(func.count()).select_from(Document).where(Document.is_demo.is_(True))) or 0
    )
    by_category = db.execute(
        select(Document.category, func.count())
        .group_by(Document.category)
        .order_by(func.count().desc())
    ).all()

    return {
        "documents": total,
        "real": total - demo,
        "demo": demo,
        "real_share": round((total - demo) / total, 4) if total else None,
        "by_category": {str(category.value): count for category, count in by_category},
    }


@router.get("/corpus/documents", summary="Browse the corpus")
def list_documents(
    db: DbSession,
    category: str | None = Query(None),
    search: str | None = Query(None, min_length=2, max_length=120),
    limit: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    include_demo: bool = Query(True),
) -> dict[str, Any]:
    statement = select(Document).order_by(Document.title)
    if category:
        statement = statement.where(Document.category == category.lower())
    if search:
        statement = statement.where(Document.title.ilike(f"%{search}%"))
    statement = _demo_filter(statement, Document, include_demo)

    page = _page(db, statement, limit, offset)
    page["items"] = [
        {
            "id": str(d.id),
            "doc_id": d.doc_id,
            "title": d.title,
            "category": d.category.value,
            "source_type": d.source_type.value,
            "source_url": d.source_url,
            "is_demo": d.is_demo,
            "demo_reason": getattr(d, "demo_reason", None),
        }
        for d in page["items"]
    ]
    return page


@router.get("/corpus/documents/{document_id}", summary="One document")
def get_document(document_id: uuid.UUID, db: DbSession) -> dict[str, Any]:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such document")
    return {
        "id": str(document.id),
        "doc_id": document.doc_id,
        "title": document.title,
        "category": document.category.value,
        "source_type": document.source_type.value,
        "source_url": document.source_url,
        "local_path": getattr(document, "local_path", None),
        "is_demo": document.is_demo,
        "demo_reason": getattr(document, "demo_reason", None),
        "word_count": getattr(document, "word_count", None),
    }
