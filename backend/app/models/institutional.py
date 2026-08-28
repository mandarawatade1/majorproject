"""Institutional entities — the tables behind the portal's public pages.

Every table here carries `is_demo`. Most rows will be false, because most of
this comes from pce.ac.in; the flag exists so that a figure the institute has
not published (a placement statistic, a fee) can be shown with a DEMO badge
rather than silently presented as fact.

Real values already confirmed from the live site are used as column comments
where they pin down what a column means — B.Tech intake is 630 across six
programmes, for instance, so `programs.intake` is per programme, not total.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import (
    AccreditationBody,
    AnnouncementCategory,
    FacilityCategory,
    ProgramLevel,
)
from app.models.mixins import DemoMixin, pg_enum, pk


class Department(Base, TimestampMixin, DemoMixin):
    """One academic department. Six B.Tech-granting ones at PCE."""

    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = pk()
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    established_year: Mapped[int | None] = mapped_column(Integer)
    hod_name: Mapped[str | None] = mapped_column(String(160))
    about: Mapped[str | None] = mapped_column(Text)
    vision: Mapped[str | None] = mapped_column(Text)
    mission: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(64))
    source_url: Mapped[str | None] = mapped_column(Text)

    programs: Mapped[list[Program]] = relationship(back_populates="department")
    faculty: Mapped[list[Faculty]] = relationship(back_populates="department")


class Program(Base, TimestampMixin, DemoMixin):
    """A degree programme.

    `choice_code` is the DTE code used in state admission counselling, e.g.
    320724510 for Computer Engineering. `intake` is the sanctioned intake for
    this programme alone — 180 for Computer Engineering, 630 across all six
    B.Tech programmes.
    """

    __tablename__ = "programs"
    __table_args__ = (
        UniqueConstraint("department_id", "level", "name", name="uq_program_dept_level_name"),
        Index("ix_programs_level", "level"),
    )

    id: Mapped[uuid.UUID] = pk()
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL")
    )
    level: Mapped[ProgramLevel] = mapped_column(
        pg_enum(ProgramLevel, "program_level"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    choice_code: Mapped[str | None] = mapped_column(String(32))
    intake: Mapped[int | None] = mapped_column(Integer)
    duration_years: Mapped[int | None] = mapped_column(Integer)
    started_year: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    curriculum_url: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)

    department: Mapped[Department | None] = relationship(back_populates="programs")
    courses: Mapped[list[Course]] = relationship(back_populates="program")


class Course(Base, TimestampMixin, DemoMixin):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("program_id", "code", name="uq_course_program_code"),
        Index("ix_courses_semester", "semester"),
    )

    id: Mapped[uuid.UUID] = pk()
    program_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE")
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    semester: Mapped[int | None] = mapped_column(Integer)
    credits: Mapped[float | None] = mapped_column(Numeric(4, 1))
    course_type: Mapped[str | None] = mapped_column(String(64))
    syllabus_url: Mapped[str | None] = mapped_column(Text)

    program: Mapped[Program | None] = relationship(back_populates="courses")


class Faculty(Base, TimestampMixin, DemoMixin):
    """A member of teaching staff.

    Names and designations come from the public directory. No personal contact
    detail is stored beyond what the institute already publishes.
    """

    __tablename__ = "faculty"
    __table_args__ = (Index("ix_faculty_name", "name"),)

    id: Mapped[uuid.UUID] = pk()
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    designation: Mapped[str | None] = mapped_column(String(160))
    qualification: Mapped[str | None] = mapped_column(String(240))
    specialisation: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(200))
    experience_years: Mapped[int | None] = mapped_column(Integer)
    profile_url: Mapped[str | None] = mapped_column(Text)
    photo_url: Mapped[str | None] = mapped_column(Text)
    publications_count: Mapped[int | None] = mapped_column(Integer)

    department: Mapped[Department | None] = relationship(back_populates="faculty")


class Announcement(Base, TimestampMixin, DemoMixin):
    __tablename__ = "announcements"
    __table_args__ = (
        Index("ix_announcements_published_at", "published_at"),
        Index("ix_announcements_category", "category"),
    )

    id: Mapped[uuid.UUID] = pk()
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    category: Mapped[AnnouncementCategory] = mapped_column(
        pg_enum(AnnouncementCategory, "announcement_category"),
        nullable=False,
        default=AnnouncementCategory.GENERAL,
    )
    published_at: Mapped[date | None] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attachment_url: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)


class Event(Base, TimestampMixin, DemoMixin):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_starts_at", "starts_at"),)

    id: Mapped[uuid.UUID] = pk()
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[date | None] = mapped_column(Date)
    ends_at: Mapped[date | None] = mapped_column(Date)
    venue: Mapped[str | None] = mapped_column(String(240))
    organiser: Mapped[str | None] = mapped_column(String(240))
    category: Mapped[str | None] = mapped_column(String(96))
    banner_url: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)


class Facility(Base, TimestampMixin, DemoMixin):
    __tablename__ = "facilities"

    id: Mapped[uuid.UUID] = pk()
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    category: Mapped[FacilityCategory] = mapped_column(
        pg_enum(FacilityCategory, "facility_category"),
        nullable=False,
        default=FacilityCategory.OTHER,
    )
    description: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)


class Placement(Base, TimestampMixin, DemoMixin):
    """Placement statistics by academic year.

    Package figures are frequently NOT published by the institute. Any row
    carrying one that was not sourced from a public page must set `is_demo`,
    which is why the flag matters more on this table than on any other.
    """

    __tablename__ = "placements"
    __table_args__ = (Index("ix_placements_year", "academic_year"),)

    id: Mapped[uuid.UUID] = pk()
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL")
    )
    academic_year: Mapped[str] = mapped_column(String(16), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(240))
    students_placed: Mapped[int | None] = mapped_column(Integer)
    highest_package: Mapped[float | None] = mapped_column(Numeric(12, 2))
    average_package: Mapped[float | None] = mapped_column(Numeric(12, 2))
    source_url: Mapped[str | None] = mapped_column(Text)


class Accreditation(Base, TimestampMixin, DemoMixin):
    """NAAC A+, NBA cycles, NIRF, UGC 2(f)/12(B), autonomous status."""

    __tablename__ = "accreditations"

    id: Mapped[uuid.UUID] = pk()
    body: Mapped[AccreditationBody] = mapped_column(
        pg_enum(AccreditationBody, "accreditation_body"), nullable=False
    )
    grade: Mapped[str | None] = mapped_column(String(64))
    scope: Mapped[str | None] = mapped_column(Text)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    certificate_url: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)


class Contact(Base, TimestampMixin, DemoMixin):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = pk()
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL")
    )
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str | None] = mapped_column(String(96))
    phone: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)


__all__ = [
    "Accreditation",
    "Announcement",
    "Contact",
    "Course",
    "Department",
    "Event",
    "Facility",
    "Faculty",
    "Placement",
    "Program",
]
