"""Classify a URL or file path into a DocumentCategory and a department.

Rules are ordered and the first match wins, so put specific patterns above
general ones. This is deliberately rule-based rather than model-based: the
institutional IA is stable and small, rules are inspectable and testable, and
an examiner can read exactly why a document was filed where it was.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from rag.ingestion.models import DocumentCategory

# --- URL path -> category. Order matters: first match wins. ----------------
_CATEGORY_RULES: list[tuple[re.Pattern[str], DocumentCategory]] = [
    (
        re.compile(r"/accreditation|/naac|/nba|/nirf|/ariia|/iqac"),
        DocumentCategory.ACCREDITATION,
    ),
    (re.compile(r"/curriculum|/syllabus|/scheme"), DocumentCategory.CURRICULUM),
    (re.compile(r"/bachelors/|/masters/|/ph-?d|/academics/"), DocumentCategory.PROGRAMME),
    (
        re.compile(r"/admission|/apply|/eligibility|/cap-round|/fee"),
        DocumentCategory.ADMISSION,
    ),
    (
        re.compile(r"/placement|/recruit|/internship|/training-and-placement"),
        DocumentCategory.PLACEMENT,
    ),
    (re.compile(r"/faculty|/staff|/profile"), DocumentCategory.FACULTY),
    (
        re.compile(r"/research|/publication|/patent|/grant|/mou"),
        DocumentCategory.RESEARCH,
    ),
    (re.compile(r"/library|/e-?resources|/journals"), DocumentCategory.LIBRARY),
    (re.compile(r"/alumni"), DocumentCategory.ALUMNI),
    (re.compile(r"/annual-report|/report|/disclosure|/audit"), DocumentCategory.REPORT),
    (re.compile(r"/event|/conference|/workshop|/seminar|/fest"), DocumentCategory.EVENT),
    (
        re.compile(r"/announcement|/notice|/notification|/news|/circular"),
        DocumentCategory.ANNOUNCEMENT,
    ),
    (
        re.compile(r"/student|/association|/council|/sports|/nss|/club"),
        DocumentCategory.STUDENT_LIFE,
    ),
    (
        re.compile(r"/governance|/committee|/board|/service-rules|/grievance"),
        DocumentCategory.GOVERNANCE,
    ),
    (re.compile(r"/contact|/reach-us|/enquiry"), DocumentCategory.CONTACT),
    (re.compile(r"/department|/dept"), DocumentCategory.DEPARTMENT),
    (
        re.compile(r"/about|/the-institute|/vision|/mission|/history|/campus"),
        DocumentCategory.INSTITUTE_PROFILE,
    ),
]

# --- URL fragment -> canonical department name ----------------------------
_DEPARTMENT_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"electronics-?(and|&)?-?computer|/ecs\b"),
        "Electronics and Computer Science",
    ),
    (
        re.compile(r"electronics-?(and|&)?-?telecomm?|/extc\b"),
        "Electronics and Telecommunication Engineering",
    ),
    (re.compile(r"computer-engineering|/comp\b|/cse?\b"), "Computer Engineering"),
    (re.compile(r"information-technology|/it\b"), "Information Technology"),
    (re.compile(r"automobile"), "Automobile Engineering"),
    (re.compile(r"mechanical|/mech\b"), "Mechanical Engineering"),
    (re.compile(r"applied-science|humanities|basic-science"), "Applied Sciences and Humanities"),
]

# Paths that are never worth ingesting: pagination, taxonomy archives, feeds,
# admin, and the WordPress plumbing that generates near-duplicate pages.
_SKIP_RULES: list[re.Pattern[str]] = [
    re.compile(r"/wp-admin|/wp-login|/wp-json|/xmlrpc\.php"),
    re.compile(r"/feed/?$|/rss|\.xml$"),
    re.compile(r"/tag/|/author/|/category/[^/]+/page/"),
    re.compile(r"/page/\d+"),
    re.compile(r"[?&](replytocom|share|print)="),
    re.compile(r"#"),
    # The extension is matched against the PATH, so a cache-busting query
    # string ("style.css?ver=6.9.7") no longer sneaks a static asset past the
    # filter and into the crawl.
    re.compile(
        r"\.(jpg|jpeg|png|gif|svg|webp|ico|css|js|zip|mp4|mp3|docx?|pptx?|xlsx?)(\?|$)", re.I
    ),
]


def categorise(url_or_path: str) -> DocumentCategory:
    """Return the best-matching category, or OTHER."""
    haystack = _normalise(url_or_path)
    for pattern, category in _CATEGORY_RULES:
        if pattern.search(haystack):
            return category
    return DocumentCategory.OTHER


def infer_department(url_or_path: str, text: str | None = None) -> str | None:
    """Return a canonical department name, or None.

    The URL is checked first because it is unambiguous. Falling back to the
    document text is intentionally limited to the first 2000 characters: a
    department named in passing near the end of an annual report does not make
    the whole report belong to that department.
    """
    haystack = _normalise(url_or_path)
    for pattern, name in _DEPARTMENT_RULES:
        if pattern.search(haystack):
            return name

    if text:
        head = _normalise(text[:2000])
        for pattern, name in _DEPARTMENT_RULES:
            if pattern.search(head):
                return name
    return None


def should_skip(url: str) -> bool:
    """True if this URL is not worth fetching."""
    return any(rule.search(url) for rule in _SKIP_RULES)


def is_pdf_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def _normalise(value: str) -> str:
    """Fold URLs and prose into one shape so the same rules match both.

    The rules are written URL-style ("computer-engineering"), but they are also
    applied to document text, where the same name appears as "Computer
    Engineering". Collapsing whitespace and underscores to hyphens lets one
    ruleset serve both without duplicating every pattern.
    """
    return re.sub(r"[\s_]+", "-", value.lower())
