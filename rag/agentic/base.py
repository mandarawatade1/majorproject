"""State carried through the C4 agent graph.

`AgentState` is a plain dataclass with no LangGraph import, so every rule that
governs the loop — deduplication, when to stop, what gets recorded — is
testable without a graph runtime, a model, or a network call. `graph.py` only
wires these transitions together.

The state exists to answer three questions at the end of a run: what did we
retrieve in total, what did we search for to get it, and how many rounds did it
take. Those map onto `RetrievalResult.hits`, `.rewritten_queries` and
`.iteration_count`, which already existed for exactly this purpose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from rag.indexing.base import IndexedHit


class StopReason(StrEnum):
    """Why the loop ended.

    Recorded rather than inferred. "The agent stopped after two rounds" means
    something quite different if it stopped because the model said it had
    enough than if it stopped because the model produced unparseable output —
    and the second case is a silent degradation to C3 that has to be visible in
    the evaluation rather than hidden inside an averaged score.
    """

    MODEL_SAYS_READY = "model_says_ready"
    ITERATION_CAP = "iteration_cap"
    NO_NEW_CHUNKS = "no_new_chunks"
    REPEATED_QUERY = "repeated_query"
    UNPARSEABLE_DECISION = "unparseable_decision"


@dataclass(slots=True)
class AgentIteration:
    """One round of the loop, recorded for the retrieval log."""

    index: int
    query: str
    hits_returned: int = 0
    new_chunks: int = 0
    decision_raw: str | None = None
    decision: str | None = None
    latencies: dict[str, float] = field(default_factory=dict)

    def to_log(self) -> dict[str, Any]:
        return {
            "iteration": self.index,
            "query": self.query,
            "hits_returned": self.hits_returned,
            "new_chunks": self.new_chunks,
            "decision": self.decision,
            "decision_raw": (self.decision_raw or "")[:200],
            "latencies_ms": {k: round(v, 1) for k, v in self.latencies.items()},
        }


@dataclass(slots=True)
class AgentState:
    """Everything the loop accumulates."""

    question: str
    max_iterations: int = 3
    top_k: int = 20

    hits: list[IndexedHit] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    iterations: list[AgentIteration] = field(default_factory=list)

    dense_hits: list[IndexedHit] = field(default_factory=list)
    sparse_hits: list[IndexedHit] = field(default_factory=list)
    """Per-arm unions across every round.

    `RetrievalResult` keeps these because, in its own words, every ablation
    number in Chapter 4 is a query over those rows — a retriever that returned
    only its winners makes the comparison unmeasurable. C4 must therefore fill
    them like C2 and C3 do, or a C4 row silently loses the breakdown that a C3
    row has, and no query can ask what BM25 contributed under the agent.
    """

    pending_query: str | None = None
    done: bool = False
    stop_reason: StopReason | None = None
    filters_applied: dict[str, Any] = field(default_factory=dict)

    _seen: set[str] = field(default_factory=set, repr=False)
    _seen_dense: set[str] = field(default_factory=set, repr=False)
    _seen_sparse: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        # The original question is the first query. Recording it here means
        # `queries[0]` is always the question and `queries[1:]` is always the
        # follow-ups, which is what feeds `rewritten_queries`.
        if not self.queries:
            self.queries = [self.question]
        if self.pending_query is None:
            self.pending_query = self.question

    # --- Accumulation -------------------------------------------------

    def add_hits(self, hits: list[IndexedHit]) -> int:
        """Merge new hits, skipping any chunk already gathered.

        Returns the count of genuinely new chunks. Deduplication is by
        `chunk_id` and preserves discovery order, so a chunk found in round one
        keeps its position rather than being reshuffled by a later round. The
        reranker downstream decides final order; this only decides membership.
        """
        return _merge(self.hits, self._seen, hits)

    def add_arm_hits(self, dense: list[IndexedHit], sparse: list[IndexedHit]) -> None:
        """Accumulate the per-arm unions, deduplicated the same way.

        Kept as unions rather than per-iteration lists because that is the
        shape `retrieval_logs` already stores for every other configuration.
        The round-by-round detail is not lost — it lives in `iterations`.
        """
        _merge(self.dense_hits, self._seen_dense, dense)
        _merge(self.sparse_hits, self._seen_sparse, sparse)

    def has_searched(self, query: str) -> bool:
        """Has this query already been issued, ignoring case and spacing?

        A quantized model asked "do you need more?" will often propose the
        query it just ran. Without this check the agent spends its whole budget
        retrieving the same chunks.
        """
        normalised = " ".join(query.lower().split())
        return any(" ".join(q.lower().split()) == normalised for q in self.queries)

    def finish(self, reason: StopReason) -> None:
        self.done = True
        self.stop_reason = reason
        self.pending_query = None

    # --- Derived ------------------------------------------------------

    @property
    def iteration_count(self) -> int:
        return len(self.iterations)

    @property
    def follow_up_queries(self) -> list[str]:
        """Queries beyond the original question — what `rewritten_queries` wants."""
        return self.queries[1:]

    @property
    def at_cap(self) -> bool:
        return len(self.iterations) >= self.max_iterations

    @property
    def merged_latencies(self) -> dict[str, float]:
        """Per-iteration latencies, suffixed so nothing is overwritten.

        C4 runs several retrievals and several decide calls. Collapsing them
        into one `dense_search` key would under-report the cost of the very
        thing C4 adds, and the plan commits to reporting latency alongside
        accuracy.
        """
        merged: dict[str, float] = {}
        for iteration in self.iterations:
            for stage, value in iteration.latencies.items():
                merged[f"{stage}_{iteration.index}"] = value
        return merged

    def to_log(self) -> list[dict[str, Any]]:
        return [iteration.to_log() for iteration in self.iterations]


def _merge(target: list[IndexedHit], seen: set[str], hits: list[IndexedHit]) -> int:
    """Append hits not already present, by chunk_id, preserving discovery order.

    Returns how many were genuinely new. Order is deliberately discovery order,
    not score order: a chunk found in round one keeps its position rather than
    being reshuffled by a later round. Membership is this function's job;
    ordering is the reranker's.
    """
    added = 0
    for hit in hits:
        if hit.chunk_id in seen:
            continue
        seen.add(hit.chunk_id)
        target.append(hit)
        added += 1
    return added


__all__ = ["AgentIteration", "AgentState", "StopReason"]
