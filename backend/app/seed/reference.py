"""Verified institutional reference data.

Everything in this module was read from a public page on pce.ac.in and is
recorded with the URL it came from. It is hard-coded rather than scraped
because it is small, slow-changing, structural data that the portal's pages are
built around — and because a wrong intake number is the kind of error an
examiner will notice immediately, so it is worth having it pinned, sourced and
reviewable in one file rather than inferred from HTML on every run.

Anything NOT confirmed from a public page does not belong here. If a figure is
needed that the institute has not published, it goes in `corpus/demo/` with a
`demo_reason`, not in this file with a guess.

Sources:
    https://www.pce.ac.in/about/the-institute/
    https://www.pce.ac.in/academics/bachelors/
    https://www.pce.ac.in/accreditation/naac/
    https://www.pce.ac.in/accreditation/nba/
"""

from __future__ import annotations

from typing import Any

INSTITUTE_URL = "https://www.pce.ac.in/about/the-institute/"
BACHELORS_URL = "https://www.pce.ac.in/academics/bachelors/"

# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------

DEPARTMENTS: list[dict[str, Any]] = [
    {
        "code": "CE",
        "name": "Computer Engineering",
        "slug": "computer-engineering",
        "established_year": 1999,
        "source_url": BACHELORS_URL,
    },
    {
        "code": "IT",
        "name": "Information Technology",
        "slug": "information-technology",
        "established_year": 1999,
        "source_url": BACHELORS_URL,
    },
    {
        "code": "EXTC",
        "name": "Electronics and Telecommunication Engineering",
        "slug": "electronics-and-telecommunication-engineering",
        "established_year": 2007,
        "source_url": BACHELORS_URL,
    },
    {
        "code": "ECS",
        "name": "Electronics and Computer Science",
        "slug": "electronics-computer-science",
        "established_year": 1999,
        "source_url": BACHELORS_URL,
    },
    {
        "code": "AUTO",
        "name": "Automobile Engineering",
        "slug": "automobile-engineering",
        "established_year": 2009,
        "source_url": BACHELORS_URL,
    },
    {
        "code": "MECH",
        "name": "Mechanical Engineering",
        "slug": "mechanical-engineering",
        "established_year": 2002,
        "source_url": BACHELORS_URL,
    },
]

# ---------------------------------------------------------------------------
# B.Tech programmes
#
# Sanctioned intake totals 630 across these six. `choice_code` is the DTE code
# used in state admission counselling.
# ---------------------------------------------------------------------------

BTECH_PROGRAMS: list[dict[str, Any]] = [
    {
        "department_code": "CE",
        "name": "Computer Engineering",
        "slug": "btech-computer-engineering",
        "choice_code": "320724510",
        "intake": 180,
        "started_year": 1999,
        "curriculum_url": "https://www.pce.ac.in/bachelors/computer-engineering/curriculum/",
    },
    {
        "department_code": "IT",
        "name": "Information Technology",
        "slug": "btech-information-technology",
        "choice_code": "320724610",
        "intake": 120,
        "started_year": 1999,
        "curriculum_url": "https://www.pce.ac.in/bachelors/information-technology/curriculum/",
    },
    {
        "department_code": "EXTC",
        "name": "Electronics and Telecommunication Engineering",
        "slug": "btech-electronics-and-telecommunication-engineering",
        "choice_code": "320737210",
        "intake": 120,
        "started_year": 2007,
        "curriculum_url": (
            "https://www.pce.ac.in/bachelors/"
            "electronics-and-telecommunication-engineering/curriculum/"
        ),
    },
    {
        "department_code": "ECS",
        "name": "Electronics and Computer Science",
        "slug": "btech-electronics-computer-science",
        "choice_code": "320790010",
        "intake": 90,
        "started_year": 1999,
        "curriculum_url": "https://www.pce.ac.in/bachelors/electronics-computer-science/curriculum/",
    },
    {
        "department_code": "AUTO",
        "name": "Automobile Engineering",
        "slug": "btech-automobile-engineering",
        "choice_code": "320760210",
        "intake": 60,
        "started_year": 2009,
        "curriculum_url": "https://www.pce.ac.in/bachelors/automobile-engineering/curriculum/",
    },
    {
        "department_code": "MECH",
        "name": "Mechanical Engineering",
        "slug": "btech-mechanical-engineering",
        "choice_code": "320761210",
        "intake": 60,
        "started_year": 2002,
        "curriculum_url": "https://www.pce.ac.in/bachelors/mechanical-engineering/curriculum/",
    },
]

TOTAL_BTECH_INTAKE = 630
"""Stated on the bachelors page. Asserted by the seed against the sum above,
so a typo in one programme's intake fails loudly rather than quietly."""


# ---------------------------------------------------------------------------
# Accreditation and recognition
# ---------------------------------------------------------------------------

ACCREDITATIONS: list[dict[str, Any]] = [
    {
        "body": "naac",
        "grade": "A+",
        "scope": "Institutional accreditation",
        "source_url": "https://www.pce.ac.in/accreditation/naac/",
    },
    {
        "body": "nba",
        "grade": "Accredited",
        "scope": (
            "Six undergraduate programmes. First accredited 2008; "
            "re-accredited 2015, 2018 and 2022."
        ),
        "source_url": "https://www.pce.ac.in/accreditation/nba/",
    },
    {
        "body": "ugc",
        "grade": "Recognised",
        "scope": (
            "Sections 2(f) and 12(B) since 2015. Autonomous status granted "
            "from academic year 2021-22."
        ),
        "source_url": INSTITUTE_URL,
    },
    {
        "body": "aicte",
        "grade": "Approved",
        "scope": "All programmes, approved by AICTE, New Delhi.",
        "source_url": INSTITUTE_URL,
    },
]


# ---------------------------------------------------------------------------
# Institute profile — used by the About page and as a small factual anchor for
# the assistant.
# ---------------------------------------------------------------------------

INSTITUTE_FACTS: dict[str, Any] = {
    "name": "Pillai College of Engineering",
    "established_year": 1999,
    "courses_commenced": "2000-01",
    "trust": "Mahatma Education Society",
    "trust_founded": 1970,
    "former_name": "Pillai Institute of Information Technology, Engineering, "
    "Media Studies and Research (PIIT), renamed 2016",
    "affiliation": "University of Mumbai",
    "autonomous_since": "2021-22",
    "campus": "Dr. K.M. Vasudevan Pillai Campus, New Panvel, Navi Mumbai",
    "campus_acres": 16,
    "built_up_sq_ft": 230000,
    "students": "2,700+",
    "btech_programmes": 6,
    "mtech_specialisations": 4,
    "phd_centres": 3,
    "source_url": INSTITUTE_URL,
}


__all__ = [
    "ACCREDITATIONS",
    "BTECH_PROGRAMS",
    "DEPARTMENTS",
    "INSTITUTE_FACTS",
    "TOTAL_BTECH_INTAKE",
]
