"""Database seeding.

    python -m app.seed              # reference data, corpus, admin
    python -m app.seed corpus       # one step

Every step is idempotent. Reference data comes from `reference.py`, which holds
only facts confirmed from a public page on pce.ac.in, each with its source URL.
Corpus data comes from `corpus/manifest.json`, carrying `is_demo` forward from
the parser rather than deciding it again.
"""

from app.seed.corpus import LoadReport, load_corpus

__all__ = ["LoadReport", "load_corpus"]
