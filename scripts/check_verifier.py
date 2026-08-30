#!/usr/bin/env python3
"""Does C5's verifier actually discriminate, or does it just agree?

A verifier that returns SUPPORTED for everything is indistinguishable from no
verifier at all, and it would look like a success in every aggregate: 100%
support rate, zero refusals, a clean Chapter 4 row. The only way to tell the
difference is to hand it answers whose correct verdict is known in advance.

So this holds the context fixed and varies the answer, which is the opposite of
what the pipeline does. Four cases, chosen to fail in different directions:

  1. an answer the context supports              -> SUPPORTED
  2. an answer the context contradicts           -> UNSUPPORTED, and refused
  3. one true sentence and one fabricated        -> PARTIALLY_SUPPORTED, only #2
  4. a fact plus a non-factual signpost          -> the signpost is not flagged

Case 3 is the one that matters most. Cases 1 and 2 can both be passed by a
model that keys off some surface feature of the whole answer; only case 3
requires judging sentences separately, which is what C5 claims to do.

Case 4 guards the opposite failure. A verifier that flags "contact the
admissions office" as unsupported would drag the support rate down on almost
every answer and make the metric meaningless.

Run inside the api container, where Ollama is reachable:

    docker compose exec api python scripts/check_verifier.py

Takes roughly one generation per case. No retrieval, no Chroma, no indexing.
"""

from __future__ import annotations

import sys

from rag.factory import build_generator
from rag.generation.prompts import assemble_context
from rag.indexing.base import IndexedHit
from rag.verification.base import Verdict
from rag.verification.claim_check import ClaimVerifier

CONTEXT_TEXT = (
    "COURSES AND INTAKE 2023-24. BACHELOR OF TECHNOLOGY. "
    "Computer Engineering: 180. Information Technology: 120. "
    "Mechanical Engineering: 60. Electronics and Telecommunication: 60. "
    "The institute is affiliated to the University of Mumbai."
)


def _context():
    return assemble_context(
        [
            IndexedHit(
                chunk_id="c1",
                content=CONTEXT_TEXT,
                score=1.0,
                metadata={
                    "document_id": "pce-pdf-1-courses-intake",
                    "document_title": "Courses Intake",
                    "section_path": "BACHELOR OF TECHNOLOGY",
                    "page_number": 1,
                    "is_demo": False,
                },
            )
        ]
    )


CASES = [
    {
        "name": "supported answer",
        "question": "What is the intake for Computer Engineering?",
        "answer": "The intake for Computer Engineering is 180 students [S1].",
        "expect_verdict": Verdict.SUPPORTED,
        "expect_unsupported": [],
        "why": "the context states 180 outright",
    },
    {
        "name": "contradicted answer",
        "question": "What is the intake for Computer Engineering?",
        "answer": "The intake for Computer Engineering is 900 students [S1].",
        "expect_verdict": Verdict.UNSUPPORTED,
        "expect_unsupported": [1],
        "why": "the context says 180, not 900 — and this must also refuse",
    },
    {
        "name": "one true, one fabricated",
        "question": "Tell me about the Computer Engineering programme.",
        "answer": (
            "The intake for Computer Engineering is 180 students [S1]. "
            "The programme has been ranked first in Maharashtra since 2019 [S1]."
        ),
        "expect_verdict": Verdict.PARTIALLY_SUPPORTED,
        "expect_unsupported": [2],
        "why": "sentence 1 is in the context, sentence 2 is invented",
    },
    {
        "name": "fact plus a non-factual signpost",
        "question": "What is the intake for Computer Engineering?",
        "answer": (
            "The intake for Computer Engineering is 180 students [S1]. "
            "For further details, please contact the admissions office."
        ),
        "expect_verdict": Verdict.SUPPORTED,
        "expect_unsupported": [],
        "why": "a signpost asserts no fact, so it can never be unsupported",
    },
]


def main() -> int:
    verifier = ClaimVerifier(generator=build_generator())
    context = _context()

    print("Checking whether C5's verifier discriminates")
    print("=" * 72)
    print(f"Context held fixed:\n  {CONTEXT_TEXT}\n")

    passed = 0
    for index, case in enumerate(CASES, start=1):
        print(f"[{index}/{len(CASES)}] {case['name']}")
        print(f"    expecting {case['expect_verdict'].value} — {case['why']}")

        result = verifier.verify(case["question"], case["answer"], context)

        ok = (
            result.verdict is case["expect_verdict"]
            and result.unsupported == case["expect_unsupported"]
        )
        # The refusal is a separate claim and gets its own check: it must fire
        # for a wholly unsupported answer and must never fire otherwise.
        expect_refusal = case["expect_verdict"] is Verdict.UNSUPPORTED
        ok = ok and result.refused is expect_refusal

        passed += ok
        print(
            f"    got       {result.verdict.value}, "
            f"unsupported={result.unsupported}, refused={result.refused}, "
            f"raw={result.raw!r}"
        )
        print(f"    {'PASS' if ok else 'FAIL'}  ({result.latency_ms / 1000:.0f}s)\n")

    print("=" * 72)
    print(f"{passed}/{len(CASES)} cases behaved as expected")

    if passed == len(CASES):
        print("\nThe verifier discriminates. C5's support rate means something.")
        return 0

    print(
        "\nThe verifier does NOT discriminate reliably.\n"
        "Read the raw replies above before running a full evaluation: a support\n"
        "rate produced by a verifier that cannot disagree is not evidence of\n"
        "grounding, it is evidence of a verifier that always says yes."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
