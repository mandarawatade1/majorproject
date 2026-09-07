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
import re
import statistics
import sys

# (question, expected source substring, note)
#
# The expectation is matched against title + section path + URL, lower-cased.
# "" means: nothing in the corpus answers this, and retrieving confidently is
# itself the failure -- these are the controls that catch a system which
# always finds something.
CASES_DIRECT: list[tuple[str, str, str]] = [
    # --- syllabus PDFs: the documents that were unreachable before ---------
    ("What subjects are in Semester I of Mechanical Engineering?",
     "mechanical-engineering-scheme-with-syllabus::semester i", "syllabus"),
    ("What is course code MATH 101?",
     "computer-engineering-curriculum", "syllabus"),
    ("Which subjects are in Semester III of B.Tech Information Technology?",
     "b.tech-it-syllabus::semester iii", "syllabus"),
    ("What subjects are in Semester IV of Electronics and Computer Science?",
     "ecs-syllabus::semester iv", "syllabus"),
    ("What subjects are in Semester V of Mechanical Engineering?",
     "mechanical-engineering-scheme-with-syllabus::semester v", "syllabus"),
    # student vocabulary rather than document vocabulary -- known gap
    ("What subjects are in first year Mechanical Engineering?",
     "mechanical-engineering-scheme-with-syllabus::semester i", "vocabulary"),
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

# The same facts, asked the way someone actually types rather than the way the
# documents are written. No question here repeats a heading, a document title
# or the institution's own vocabulary. This measures whether retrieval survives
# paraphrase, which is the difference between a system that works and one that
# works when you already know what it calls things.
CASES_LOOSE: list[tuple[str, str, str]] = [
    ("how much does it cost to study computer engineering there",
     "bachelor-of-technology-computer-engineering", "fees"),
    ("what's the price of the mechanical course per year",
     "bachelor-of-technology-mechanical-engineering", "fees"),
    ("is automobile branch expensive",
     "bachelor-of-technology-automobile-engineering", "fees"),

    ("what will I study in my first year of mech",
     "mechanical-engineering-scheme-with-syllabus::semester i", "syllabus"),
    ("which papers do computer students have to clear",
     "computer-engineering-curriculum", "syllabus"),

    ("can I join if I did commerce in 12th",
     "bachelor-of-technology", "eligibility"),
    ("what marks do I need to get in",
     "bachelor-of-technology", "eligibility"),

    ("what test do I have to give to get admission",
     "pillai.edu.in", "admissions"),
    ("how do I apply",
     "pillai.edu.in/admissions", "admissions"),
    ("is there any money help for good students",
     "scholarship", "pce"),

    ("what branches can I take",
     "engineering", "pce"),
    ("do they help with jobs after the course",
     "placement", "pce"),
]


def matches(expected: str, text: str) -> bool:
    """Does this hit satisfy the expectation?

    `expected` is either a document fragment, or "document::section". The
    second form is what makes the measurement mean anything: retrieving the
    right document is not success if it is the wrong part of it. Asked for
    first-year subjects, this pipeline once returned the correct syllabus at
    Semester VIII -- a document-level match, and an answer that would have
    been confidently wrong.

    Section matching is word-bounded, because "semester i" is a substring of
    "semester iii" and a naive containment test would score them equal.
    """
    if "::" not in expected:
        return expected in text
    document, section = expected.split("::", 1)
    if document not in text:
        return False
    return re.search(rf"\b{re.escape(section)}\b", text) is not None


def describe(hit) -> str:
    """Short, human-readable identification of a hit, for failure output."""
    meta = hit.metadata or {}
    return " | ".join(
        str(meta.get(key, ""))
        for key in ("document_title", "section_path", "source_url")
    ).lower()


def haystack(hit) -> str:
    """Everything a match may be looked for in: metadata AND the chunk text.

    The chunk text has to be included or the comparison is rigged. C0's fixed
    chunker sets `section_path=None` by design -- a 512-character window spans
    arbitrary parts of a document and belongs to no single section -- so a test
    that reads the section only from metadata scores C0 as missing passages it
    may well have retrieved. Asking instead whether the text handed to the
    generator actually contains the answer is a question both chunkers can be
    asked on equal terms.
    """
    return describe(hit) + " || " + (hit.content or "").lower()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="C3")
    parser.add_argument("--set", default="direct",
                        choices=("direct", "loose", "all"),
                        help="direct: document vocabulary. loose: how people ask.")
    parser.add_argument("--verbose", action="store_true",
                        help="Print the final five for every case, not just failures.")
    args = parser.parse_args()

    from rag.config import get_config
    from rag.factory import build_pipeline

    pipeline = build_pipeline(get_config(args.config))

    CASES = {
        "direct": CASES_DIRECT,
        "loose": CASES_LOOSE,
        "all": CASES_DIRECT + CASES_LOOSE,
    }[args.set]

    scored = [c for c in CASES if c[1]]
    controls = [c for c in CASES if not c[1]]
    passed = pool_only = 0
    context_sizes: list[int] = []
    dropped_counts: list[int] = []
    failures: list[tuple[str, str, str, list[str]]] = []
    control_notes: list[tuple[str, list[str]]] = []

    print(f"config {args.config} · set={args.set} · {len(CASES)} questions "
          f"({len(scored)} scored, {len(controls)} controls)\n")

    for question, expected, note in CASES:
        prepared = pipeline.prepare(question)
        retrieval = prepared.retrieval

        # What the generator is actually given -- not what retrieval returned.
        # The two differ, and the difference is not uniform across
        # configurations. C2 retrieves 20 chunks and applies no reranking, so
        # scoring its full hit list would credit it for passages that
        # `assemble_context` drops at the 8,000-character budget and the model
        # never sees. C3 retrieves the same 20 and reranks to 5, all of which
        # fit. Measuring the assembled context is the only comparison in which
        # every configuration is asked the same question.
        final = prepared.context.sources
        shown = [haystack(h) for h in final]
        pool = [haystack(h) for h in retrieval.hits]
        labels = [describe(h) for h in final]
        context_sizes.append(prepared.context.included)
        dropped_counts.append(prepared.context.dropped_for_budget)

        if not expected:
            control_notes.append((question, labels))
            print(f"  ~  [{note}] {question}")
            continue

        in_final = any(matches(expected, s) for s in shown)
        in_pool = any(matches(expected, s) for s in pool)

        if in_final:
            passed += 1
            mark = "PASS"
        elif in_pool:
            pool_only += 1
            mark = "POOL"   # retrieved, but never reached the generator
            failures.append((question, expected, note, labels))
        else:
            mark = "MISS"   # never retrieved at all
            failures.append((question, expected, note, labels))

        print(f"  {mark} [{note}] {question}")
        if args.verbose:
            for line in labels:
                print(f"         {line[:120]}")

    total = len(scored)
    print(f"\n{'='*72}")
    print(f"context: {statistics.mean(context_sizes):.1f} chunks shown on average, "
          f"{sum(dropped_counts)} chunk-drops at the {pipeline.config.max_context_chars}-char budget")
    print(f"in final context : {passed}/{total}")
    # Two distinct causes: reranking discarded it (C3+), or the 8,000-char
    # context budget cut it (any configuration whose chunks are large enough,
    # which in practice means the structure-aware ones).
    print(f"retrieved, not shown to the model : {pool_only}")
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
