"""Prompt assembly, shared by every configuration.

Shared on purpose. If C0 and C5 used differently worded prompts, a measured
difference between them would include the wording, and no claim about
structure-aware chunking or hybrid retrieval could be separated from it. So
there is exactly one context format and one prompt builder, and the only thing
`PipelineConfig` changes is whether citation and refusal instructions are
present.

That single difference is itself part of the comparison: C0 is a naive system
that answers from context without being told to ground itself, which is
precisely the behaviour whose hallucination rate the project measures against.
"""

from __future__ import annotations

from dataclasses import dataclass

from rag.indexing.base import IndexedHit

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

BASE_SYSTEM = (
    "You are an assistant for Pillai College of Engineering, New Panvel. "
    "You answer questions about the institution using the context provided."
)

GROUNDED_SYSTEM = (
    BASE_SYSTEM + "\n\n"
    "Rules you must follow:\n"
    "1. Answer ONLY from the numbered context below. Do not use outside knowledge.\n"
    "2. Attach a citation marker such as [S1] to every factual sentence, naming "
    "the source it came from. A sentence with a fact and no marker is an error.\n"
    "3. If the context does not contain the answer, say so plainly and suggest "
    "where the reader might look instead. Do not guess, and do not fill a gap "
    "with something plausible.\n"
    "4. If sources disagree, say that they disagree and cite both.\n"
    "5. Sources marked [DEMO DATA] are synthetic examples, not real "
    "institutional fact. If you use one, say so in your answer."
)

REFUSAL_TEXT = "I cannot answer that from the institutional documents available to me."


@dataclass(slots=True)
class AssembledContext:
    """The context block, plus the mapping a citation resolves through."""

    text: str
    sources: list[IndexedHit]
    included: int
    dropped_for_budget: int
    contains_demo: bool

    @property
    def is_empty(self) -> bool:
        return self.included == 0


def assemble_context(hits: list[IndexedHit], max_chars: int = 8000) -> AssembledContext:
    """Render retrieved chunks as a numbered context block.

    Markers are assigned by rank, so [S1] is always the top-ranked chunk. The
    order is stable and recorded, because `message_citations` resolves a marker
    back to a chunk id and a wrong mapping would attach a real page number to
    the wrong claim — a worse failure than having no citation at all.
    """
    blocks: list[str] = []
    included: list[IndexedHit] = []
    used = 0
    dropped = 0

    for position, hit in enumerate(hits, start=1):
        header = f"[S{position}] {hit.citation_label()}"
        block = f"{header}\n{hit.content.strip()}"

        if used + len(block) > max_chars and included:
            # Budget exhausted. Counted rather than silently discarded: a
            # question answered from three of five retrieved chunks was
            # answered from less than retrieval provided, and Chapter 4 needs
            # to be able to see that.
            dropped = len(hits) - len(included)
            break

        blocks.append(block)
        included.append(hit)
        used += len(block)

    return AssembledContext(
        text="\n\n".join(blocks),
        sources=included,
        included=len(included),
        dropped_for_budget=dropped,
        contains_demo=any(hit.is_demo for hit in included),
    )


def build_prompt(
    question: str,
    context: AssembledContext,
    *,
    enforce_citations: bool = False,
) -> tuple[str, str]:
    """Return (system, prompt).

    `enforce_citations` is the only thing a configuration changes here. Off is
    C0: answer from context, with no instruction to ground or to refuse.
    """
    system = GROUNDED_SYSTEM if enforce_citations else BASE_SYSTEM

    if context.is_empty:
        body = (
            "No context was retrieved for this question.\n\n"
            f"Question: {question}\n\n"
            "State that you have no information on this rather than answering "
            "from general knowledge."
        )
        return system, body

    instruction = (
        "Answer the question using only the context above, citing each fact "
        "with its [Sn] marker."
        if enforce_citations
        else "Answer the question using the context above."
    )

    body = f"Context:\n{context.text}\n\nQuestion: {question}\n\n{instruction}"
    return system, body


def format_sources(context: AssembledContext) -> str:
    """A human-readable source list to print under an answer."""
    if context.is_empty:
        return "Sources: none retrieved"

    lines = ["Sources:"]
    for position, hit in enumerate(context.sources, start=1):
        lines.append(f"  [S{position}] {hit.citation_label()}")
        url = hit.metadata.get("source_url")
        if url:
            lines.append(f"        {url}")
    if context.contains_demo:
        lines.append(
            "\n  NOTE: one or more sources are synthetic DEMO DATA and do not "
            "describe real institutional fact."
        )
    if context.dropped_for_budget:
        lines.append(
            f"\n  {context.dropped_for_budget} retrieved chunk(s) omitted for context budget."
        )
    return "\n".join(lines)


__all__ = [
    "BASE_SYSTEM",
    "GROUNDED_SYSTEM",
    "REFUSAL_TEXT",
    "AssembledContext",
    "assemble_context",
    "build_prompt",
    "format_sources",
]
