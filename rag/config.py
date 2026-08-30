"""PipelineConfig — the object that defines configurations C0 through C5.

This is the single most important type in the knowledge service, and it exists
for one reason: **the Chapter 4 comparison has to vary one thing at a time.**

The alternative — writing a "baseline script" and a "proposed script" — looks
easier and produces a worthless result. Two separately written programs differ
in a hundred incidental ways: prompt wording, context assembly, token budget,
retry behaviour. A measured difference between them cannot be attributed to
structure-aware chunking or to hybrid retrieval, because it also includes every
accident of how each was written.

Here, C0 and C5 run the *same* orchestrator over the *same* corpus with the
*same* prompt assembly. The only differences are the ones this object declares.
So when C2 scores higher than C1 on context precision, the cause is hybrid
retrieval, because nothing else changed.

    C0  fixed chunks, dense-only, top-5, no citations   <- the naive baseline
    C1  + structure-aware semantic chunking
    C2  + hybrid retrieval (dense + BM25, fused with RRF)
    C3  + cross-encoder reranking
    C4  + agentic planner-executor
    C5  + post-answer verification                       <- the full system

One honest exception, found by auditing the code rather than reading this list:
**C0 -> C1 changes two things**, because C1 also turns on `enforce_citations`,
which swaps the system prompt. C1_CONTROL exists to separate them, and the
distinction is spelled out where that configuration is defined. Note what that
means about `innovations_enabled` below: it reports the *curated* list, so it
will say "one innovation" however many fields a configuration actually changes.
It is a label for results, not a check on the ablation — the check lives in the
tests, comparing dataclass fields.

Phase 3 implements C0. C1 through C5 are declared here already so the shape of
the comparison is fixed before any of it is built, rather than being
reverse-engineered from whatever got implemented.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any


class ChunkingStrategy(StrEnum):
    FIXED = "fixed"
    """Split every N characters regardless of meaning. Deliberately naive: this
    is the thing the project claims to improve on, so it has to exist and work
    properly rather than being a strawman."""

    STRUCTURE_AWARE = "structure_aware"
    """Split on the document's own heading hierarchy, never across a section
    boundary, with semantic breakpoints inside long sections. Phase 4."""


class RetrievalStrategy(StrEnum):
    DENSE = "dense"
    """Vector similarity only."""

    HYBRID = "hybrid"
    """Dense and BM25 in parallel, fused with Reciprocal Rank Fusion. Phase 4."""


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """One configuration of the pipeline. Frozen, so a run cannot mutate the
    configuration it is being measured under."""

    name: str
    description: str

    # --- Chunking ---
    chunking: ChunkingStrategy = ChunkingStrategy.FIXED
    chunk_size_chars: int = 512
    chunk_overlap_chars: int = 64
    chunk_min_tokens: int = 256
    chunk_max_tokens: int = 800

    # --- Retrieval ---
    retrieval: RetrievalStrategy = RetrievalStrategy.DENSE
    dense_top_k: int = 5
    sparse_top_k: int = 0
    rrf_k: int = 60
    rerank: bool = False
    rerank_top_n: int = 5

    # --- Context assembly ---
    max_context_chars: int = 8000

    # --- Generation ---
    enforce_citations: bool = False
    """When true the model must attach [Sn] markers and refuse unsupported
    claims. Off for C0: the baseline is what a naive implementation does.

    This is a real behavioural switch, not a label: it selects GROUNDED_SYSTEM
    over BASE_SYSTEM in `build_prompt`. See C1_CONTROL below for why that
    matters to the ablation.
    """

    # --- Reasoning and checking ---
    agentic: bool = False
    verify_answer: bool = False
    agent_max_iterations: int = 3

    # --- Filtering ---
    include_demo_sources: bool = True
    """Demo documents are part of the corpus by design. This exists so an
    evaluation run can exclude them and measure against real data only."""

    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------

    def with_overrides(self, **changes: Any) -> PipelineConfig:
        """A copy with fields changed — for one-off experiments without
        editing a preset that other results were measured under."""
        return replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        """Serialised into `eval_runs.config` and `retrieval_logs`, so any
        recorded result can be traced back to exactly how it was produced."""
        return {
            "name": self.name,
            "chunking": self.chunking.value,
            "chunk_size_chars": self.chunk_size_chars,
            "chunk_overlap_chars": self.chunk_overlap_chars,
            "retrieval": self.retrieval.value,
            "dense_top_k": self.dense_top_k,
            "sparse_top_k": self.sparse_top_k,
            "rrf_k": self.rrf_k,
            "rerank": self.rerank,
            "rerank_top_n": self.rerank_top_n,
            "max_context_chars": self.max_context_chars,
            "enforce_citations": self.enforce_citations,
            "agentic": self.agentic,
            "verify_answer": self.verify_answer,
            "include_demo_sources": self.include_demo_sources,
        }

    @property
    def uses_sparse(self) -> bool:
        return self.retrieval is RetrievalStrategy.HYBRID and self.sparse_top_k > 0

    @property
    def innovations_enabled(self) -> list[str]:
        """Which of the five claimed innovations this configuration turns on.

        Used by the CLI and the evaluation console so a result is always
        labelled with what produced it.
        """
        enabled = []
        if self.chunking is ChunkingStrategy.STRUCTURE_AWARE:
            enabled.append("structure-aware chunking")
        if self.retrieval is RetrievalStrategy.HYBRID:
            enabled.append("hybrid retrieval")
        if self.rerank:
            enabled.append("cross-encoder reranking")
        if self.agentic:
            enabled.append("agentic reasoning")
        if self.verify_answer:
            enabled.append("post-answer verification")
        return enabled


# ---------------------------------------------------------------------------
# The six configurations. Each adds exactly one thing to the one before it.
# ---------------------------------------------------------------------------

C0_BASELINE = PipelineConfig(
    name="C0",
    description="Naive RAG: fixed-size chunks, dense-only retrieval, top-5, no citations",
)

C1_STRUCTURE_AWARE = C0_BASELINE.with_overrides(
    name="C1",
    description="C0 + structure-aware semantic chunking with metadata enrichment",
    chunking=ChunkingStrategy.STRUCTURE_AWARE,
    enforce_citations=True,
)

C2_HYBRID = C1_STRUCTURE_AWARE.with_overrides(
    name="C2",
    description="C1 + hybrid dense and BM25 retrieval fused with RRF",
    retrieval=RetrievalStrategy.HYBRID,
    dense_top_k=20,
    sparse_top_k=20,
)

C3_RERANK = C2_HYBRID.with_overrides(
    name="C3",
    description="C2 + cross-encoder reranking",
    rerank=True,
    rerank_top_n=5,
)

C4_AGENTIC = C3_RERANK.with_overrides(
    name="C4",
    description="C3 + agentic planner-executor with iterative retrieval",
    agentic=True,
)

C5_FULL = C4_AGENTIC.with_overrides(
    name="C5",
    description="C4 + post-answer verification — the full proposed system",
    verify_answer=True,
)

# ---------------------------------------------------------------------------
# Controls. Not steps in the ablation — they exist to separate two changes
# that one step happens to make together.
# ---------------------------------------------------------------------------

C1_CONTROL = C1_STRUCTURE_AWARE.with_overrides(
    name="C1-CONTROL",
    description="C1's chunking with C0's prompt — isolates chunking from grounding",
    enforce_citations=False,
)
"""C1 changes two things at once, and this is how the report separates them.

C1 turns on structure-aware chunking *and* `enforce_citations`, and the second
is not cosmetic: it swaps BASE_SYSTEM for GROUNDED_SYSTEM and rewrites the
instruction appended to the prompt. So a C0 -> C1 improvement is chunking and
grounding combined, and a Chapter 4 row labelled "structure-aware chunking"
would be claiming more than was measured.

With this control the single step becomes two clean ones:

    C0 -> C1-CONTROL   structure-aware chunking alone (prompt held at C0's)
    C1-CONTROL -> C1   the grounding prompt alone (chunking held at C1's)

It is deliberately absent from ABLATION_ORDER. It is not a stage of the
proposed system; it is the measurement that lets the first stage be reported
honestly.
"""

CONTROL_ORDER = ["C1-CONTROL"]

CONFIGURATIONS: dict[str, PipelineConfig] = {
    c.name: c
    for c in (
        C0_BASELINE,
        C1_STRUCTURE_AWARE,
        C2_HYBRID,
        C3_RERANK,
        C4_AGENTIC,
        C5_FULL,
        C1_CONTROL,
    )
}

ABLATION_ORDER = ["C0", "C1", "C2", "C3", "C4", "C5"]
"""The proposed system's stages, in order. Controls are not members."""


def get_config(name: str) -> PipelineConfig:
    """Look up a configuration by name, case-insensitively."""
    key = name.strip().upper()
    if key not in CONFIGURATIONS:
        known = ", ".join(ABLATION_ORDER + CONTROL_ORDER)
        raise KeyError(f"unknown configuration {name!r}. Known: {known}")
    return CONFIGURATIONS[key]


def implemented_configs() -> list[str]:
    """Configurations whose stages actually exist yet.

    Asking for a configuration that is not here raises rather than silently
    running something else under its name, which would put a wrong number in
    the report under a right-looking label.

    C1-CONTROL runs entirely on stages C1 already has — only a flag differs —
    so it is buildable the moment C1 is.

    As of Phase 6 every configuration is built. The gate stays because it is
    cheap and because it caught nothing only by being kept honest: each phase
    had to move this list deliberately, which is what stopped a half-built
    stage from being measured under a finished name.
    """
    return ["C0", "C1", "C2", "C3", "C4", "C5", "C1-CONTROL"]


__all__ = [
    "ABLATION_ORDER",
    "C0_BASELINE",
    "C1_CONTROL",
    "C1_STRUCTURE_AWARE",
    "C2_HYBRID",
    "C3_RERANK",
    "C4_AGENTIC",
    "C5_FULL",
    "CONFIGURATIONS",
    "CONTROL_ORDER",
    "ChunkingStrategy",
    "PipelineConfig",
    "RetrievalStrategy",
    "get_config",
    "implemented_configs",
]
