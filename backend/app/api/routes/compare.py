"""Baseline against proposed, from the recorded evaluation runs.

Public, and deliberately reading files rather than answering live.

A page that ran C0 and C3 fresh and put the results side by side would be
showing one sample of each. The same question asked three times through this
system has produced three different citations, so a single live pair is a coin
flip presented as a measurement — and it would also cost a cold model load in
front of whoever is watching. These endpoints serve the runs Chapter 4 actually
reports, which is both cheaper and more honest.

The trade is that only the twenty evaluated questions can be compared. That is
the right limit: those are the questions with recorded results, and inviting a
visitor to compare an unevaluated one would invite them to draw a conclusion
from a sample of one.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from app.services.evaluation import EVAL_ROOT, available_configs, load_answer, questions

router = APIRouter(prefix="/compare", tags=["compare"])

# What each configuration adds, for labelling the comparison. Kept here rather
# than imported from rag.config because these are one-line descriptions for a
# visitor, not the machine-readable definitions.
CONFIG_LABELS: dict[str, str] = {
    "C0": "Baseline — fixed chunking, dense retrieval only",
    "C1": "Structure-aware chunking",
    "C1-CONTROL": "Control — grounding prompt without structure-aware chunking",
    "C2": "Hybrid retrieval (dense + BM25, fused with RRF)",
    "C3": "Cross-encoder reranking",
    "C4": "Agentic planner-executor",
    "C5": "Post-answer claim verification",
}


@router.get("", summary="What can be compared")
def index() -> dict[str, Any]:
    configs = available_configs()
    if not configs:
        # Named explicitly, because the realistic cause is a missing mount
        # rather than a missing evaluation, and the two look identical from
        # the outside.
        return {
            "configs": [],
            "questions": [],
            "note": f"no evaluation runs found under {EVAL_ROOT}",
        }

    return {
        "configs": [
            {"name": name, "description": CONFIG_LABELS.get(name, name)} for name in configs
        ],
        "questions": questions(),
        "default": {"baseline": "C0", "proposed": "C3"},
    }


@router.get("/{question_id}", summary="One question across configurations")
def compare_question(
    question_id: str,
    configs: str = Query("C0,C3", description="Comma-separated configuration names"),
) -> dict[str, Any]:
    wanted = [name.strip().upper() for name in configs.split(",") if name.strip()]
    if not 2 <= len(wanted) <= 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="compare between two and four configurations",
        )

    answers = []
    for name in wanted:
        recorded = load_answer(name, question_id)
        if recorded is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"no recorded answer for {question_id} under {name}",
            )
        answers.append({**recorded.to_dict(), "description": CONFIG_LABELS.get(name, name)})

    return {
        "question_id": question_id,
        "question": answers[0]["question"],
        "answers": answers,
    }
