#!/usr/bin/env python3
"""Measure retrieval across a fixed question set, without generation.

One question at a time cannot answer "does retrieval work". This runs a set
of questions whose correct source is known in advance and reports how often
that source reaches the context the generator is actually shown.

It deliberately stops before generation. Generation takes minutes per
question and tests something else -- whether the model uses what it was
given. This measures whether it was given the right thing at all, which is
the prior question and the cheaper one.

Usage:
    python -m rag.batchtest [--config C3] [--verbose]
"""

from __future__ import annotations

import argparse
import sys

# (question, expected source substring, note)
#
# The expectation is matched against title + section path + URL, lower-cased.
# "" means: nothing in the corpus answers this, and retrieving confidently is
# itself the failure -- these are the controls that catch a system which
# always finds something.
CASES: list[tuple[str, str, str]] = [
    # --- syllabus PDFs: the documents that were unreachable before ---------
    ("What subjects are in Semester I of Mechanical Engineering?",
     "mechanical-engineering-scheme-with-syllabus", "syllabus"),
    ("What is course code MATH 101?",
     "computer-engineering-curriculum", "syllabus"),
    ("Which subjects are in Semester III of B.Tech Information Technology?",
     "b.tech-it-syllabus", "syllabus"),
    ("What subjects are in Semester IV of Electronics and Computer Science?",
     "ecs-syllabus", "syllabus"),
    ("What subjects are in Semester V of Mechanical Engineering?",
     "mechanical-engineering-scheme-with-syllabus", "syllabus"),
    # student vocabulary rather than document vocabulary -- known gap
    ("What subjects are in first year Mechanical Engineering?",
     "mechanical-engineering-scheme-with-syllabus", "vocabulary"),
    ("What subjects are studied in the second year of Computer Engineering?",
     "computer-engineering-curriculum", "vocabulary"),

    # --- per-department fees: five near-identical pages -------------------
    ("What is the fee for B.Tech Computer Engineering?",
     "bachelor-of-technology-computer-engineering", "fees"),
    ("What is the fee for B.Tech Mechanical Engineering?",
     "bachelor-of-technology-mechanical-engineering", "fees"),
    ("What is the fee for B.Tech Automobile Engineering?",
     "bachelor-of-technology-automobile-engineering", "fees"),
    ("What is the fee for B.Tech Electronics and Computer Science?",
     "bachelor-of-technology-electronics-computer-science", "fees"),
    ("What is the fee for B.Tech Electronics and Telecommunication?",
     "bachelor-of-technology-electronics-telecommunication", "fees"),

    # --- eligibility ------------------------------------------------------
    ("What is the eligibility for B.Tech Computer Engineering?",
     "bachelor-of-technology-computer-engineering", "eligibility"),
    ("What is the eligibility for B.Tech Mechanical Engineering?",
     "bachelor-of-technology-mechanical-engineering", "eligibility"),

    # --- admissions -------------------------------------------------------
    ("What is the admission process for engineering?",
     "pillai.edu.in/admissions", "admissions"),
    ("What is the PULSE entrance exam pattern for engineering?",
     "pillai.edu.in/pulse", "admissions"),
    ("How many marks is the PULSE exam and is there negative marking?",
     "pillai.edu.in/pulse", "admissions"),

    # --- PCE's own content ------------------------------------------------
    ("Which departments does Pillai College of Engineering have?",
     "pce.ac.in", "pce"),
    ("What are the placement statistics at PCE?",
     "pce.ac.in", "pce"),
    ("What scholarships are available to students?",
     "scholarship", "pce"),

    # --- controls: nothing in the corpus answers these --------------------
    ("What is the fee for B.Tech Artificial Intelligence and Data Science?",
     "", "control"),
    ("What is the fee for B.Tech Fashion Design?",
     "", "control"),
]


def describe(hit) -> str:
    meta = hit.metadata or {}
    return " | ".join(
        str(meta.get(key, ""))
        for key in ("document_title", "section_path", "source_url")
    ).lower()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="C3")
    parser.add_argument("--verbose", action="store_true",
                        help="Print the final five for every case, not just failures.")
    args = parser.parse_args()

    from rag.config import get_config
    from rag.factory import build_pipeline

    pipeline = build_pipeline(get_config(args.config))

    scored = [c for c in CASES if c[1]]
    controls = [c for c in CASES if not c[1]]
    passed = pool_only = 0
    failures: list[tuple[str, str, str, list[str]]] = []
    control_notes: list[tuple[str, list[str]]] = []

    print(f"config {args.config} · {len(CASES)} questions "
          f"({len(scored)} scored, {len(controls)} controls)\n")

    for question, expected, note in CASES:
        prepared = pipeline.prepare(question)
        retrieval = prepared.retrieval
        final = retrieval.reranked_hits or retrieval.hits
        shown = [describe(h) for h in final]
        pool = [describe(h) for h in retrieval.hits]

        if not expected:
            control_notes.append((question, shown))
            print(f"  ~  [{note}] {question}")
            continue

        in_final = any(expected in s for s in shown)
        in_pool = any(expected in s for s in pool)

        if in_final:
            passed += 1
            mark = "PASS"
        elif in_pool:
            pool_only += 1
            mark = "POOL"   # retrieved, then discarded by reranking
            failures.append((question, expected, note, shown))
        else:
            mark = "MISS"   # never retrieved at all
            failures.append((question, expected, note, shown))

        print(f"  {mark} [{note}] {question}")
        if args.verbose:
            for line in shown:
                print(f"         {line[:120]}")

    total = len(scored)
    print(f"\n{'='*72}")
    print(f"in final context : {passed}/{total}")
    print(f"retrieved then dropped by rerank : {pool_only}")
    print(f"never retrieved  : {total - passed - pool_only}")

    if failures:
        print(f"\n--- failures ---")
        for question, expected, note, shown in failures:
            print(f"\n[{note}] {question}")
            print(f"   wanted: {expected}")
            for line in shown[:3]:
                print(f"   got   : {line[:110]}")

    print(f"\n--- controls (nothing should confidently answer these) ---")
    for question, shown in control_notes:
        print(f"\n{question}")
        for line in shown[:3]:
            print(f"   got: {line[:110]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
