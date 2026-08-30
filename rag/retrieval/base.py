"""The retrieval protocol and its result.

`RetrievalResult` carries per-stage candidate lists and timings, not just the
final hits. That is deliberate: it is what `retrieval_logs` persists, and every
ablation number in Chapter 4 is a query over those rows. A retriever that
returned only its winners would make the comparison unmeasurable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from rag.indexing.base import IndexedHit


@dataclass(slots=True)
class RetrievalResult:
    """What retrieval produced, and how it got there."""

    query: str
    hits: list[IndexedHit] = field(default_factory=list)

    rewritten_queries: list[str] = field(default_factory=list)
    dense_hits: list[IndexedHit] = field(default_factory=list)
    sparse_hits: list[IndexedHit] = field(default_factory=list)
    fused_hits: list[IndexedHit] = field(default_factory=list)
    reranked_hits: list[IndexedHit] = field(default_factory=list)

    filters_applied: dict[str, Any] = field(default_factory=dict)
    stage_latencies: dict[str, float] = field(default_factory=dict)
    iteration_count: int = 1

    # --- Populated only by the C4 agent ---
    iterations: list[dict[str, Any]] = field(default_factory=list)
    """Round-by-round detail. Empty for every single-pass configuration, so a
    C4 row in retrieval_logs is distinguishable from a C3 row by its presence."""

    stop_reason: str | None = None
    """Why the agent loop ended. Three of its five values mean C4 degraded
    towards C3 for that question, so it is recorded rather than left to be
    inferred from an averaged score."""

    def to_log(self) -> dict[str, Any]:
        """Shaped for the `retrieval_logs` row."""

        def serialise(hits: list[IndexedHit]) -> list[dict[str, Any]]:
            return [
                {
                    "chunk_id": hit.chunk_id,
                    "score": round(hit.score, 6),
                    "document_id": hit.document_id,
                    "is_demo": hit.is_demo,
                }
                for hit in hits
            ]

        return {
            "original_query": self.query,
            "rewritten_queries": self.rewritten_queries,
            "dense_hits": serialise(self.dense_hits),
            "sparse_hits": serialise(self.sparse_hits),
            "fused_hits": serialise(self.fused_hits),
            "reranked_hits": serialise(self.reranked_hits),
            "filters_applied": self.filters_applied,
            "stage_latencies": {
                k: round(v, 2) for k, v in self.stage_latencies.items()
            },
            "iteration_count": self.iteration_count,
            "iterations": self.iterations,
            "stop_reason": self.stop_reason,
        }


class Retriever(Protocol):
    name: str

    def retrieve(self, query: str, top_k: int) -> RetrievalResult: ...


class stage_timer:  # noqa: N801 - used as a context manager, reads better lowercase
    """Record how long a retrieval stage took, in milliseconds."""

    def __init__(self, result: RetrievalResult, stage: str) -> None:
        self._result = result
        self._stage = stage
        self._started = 0.0

    def __enter__(self) -> stage_timer:
        self._started = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        elapsed = (time.perf_counter() - self._started) * 1000
        self._result.stage_latencies[self._stage] = elapsed
