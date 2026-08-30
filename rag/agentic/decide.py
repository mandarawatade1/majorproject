"""The decide step: does the agent have enough, or should it search again?

Deliberately plain text rather than tool-calling or JSON. A 4-bit quantized 7B
model does not reliably emit well-formed structured output, and the failure
mode matters: a malformed JSON blob parsed leniently can silently yield "no
follow-up", turning C4 into C3 without anything erroring. A one-line contract
either matches or visibly does not, and an unmatched response is *recorded* as
unparseable rather than averaged into the results.

Everything here is a pure function over strings. The parser is where this will
actually break in practice, so it is testable without a model, a graph or a
network call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rag.agentic.base import AgentState

MAX_CONTEXT_CHARS = 3000
"""Budget for the digest shown to the decide step.

Deliberately smaller than the answer step's budget. This call is asked a yes/no
question, not asked to write an answer, and it runs once per iteration — on CPU
inference the prompt length is most of the cost.
"""

MAX_CHUNK_PREVIEW = 300


DECIDE_SYSTEM = (
    "You decide whether a search has gathered enough information to answer a "
    "question about Pillai College of Engineering.\n\n"
    "Reply with EXACTLY ONE line, in one of these two forms and nothing else:\n"
    "  READY\n"
    "  SEARCH: <a short search query>\n\n"
    "Reply READY if the excerpts already contain what is needed, or if further "
    "searching is unlikely to help.\n"
    "Reply SEARCH only if a specific fact is missing, and make the query target "
    "that missing fact — not a rephrasing of the original question.\n"
    "NEVER repeat a search that has already been run. Running it again returns "
    "the same passages and wastes the remaining budget. If the only query you "
    "can think of is one already listed, reply READY instead.\n"
    "Do not explain your choice. Do not add anything before or after the line."
)


@dataclass(slots=True)
class Decision:
    """What the decide step concluded."""

    ready: bool
    query: str | None = None
    parsed: bool = True
    raw: str = ""

    @property
    def label(self) -> str:
        if not self.parsed:
            return "UNPARSEABLE"
        return "READY" if self.ready else f"SEARCH: {self.query}"


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


def build_decide_prompt(state: AgentState) -> tuple[str, str]:
    """Return (system, prompt) for the decide step."""
    excerpts = _digest(state)
    already = "\n".join(f"  - {query}" for query in state.queries)

    remaining = state.max_iterations - len(state.iterations)
    body = (
        f"Question: {state.question}\n\n"
        f"Searches already run:\n{already}\n\n"
        f"Excerpts gathered so far ({len(state.hits)} passages):\n"
        f"{excerpts if excerpts else '  (nothing retrieved)'}\n\n"
        f"You may run at most {max(remaining, 0)} more search(es), and a "
        f"repeat of any search listed above will be rejected.\n"
        f"Reply with one line: READY, or SEARCH: <query>"
    )
    return DECIDE_SYSTEM, body


def _digest(state: AgentState) -> str:
    """A compact, budget-bounded view of what has been gathered."""
    lines: list[str] = []
    used = 0
    for position, hit in enumerate(state.hits, start=1):
        preview = " ".join(hit.content.split())[:MAX_CHUNK_PREVIEW]
        line = f"  {position}. {hit.citation_label()}\n     {preview}"
        if used + len(line) > MAX_CONTEXT_CHARS and lines:
            lines.append(f"  ... and {len(state.hits) - position + 1} more passages")
            break
        lines.append(line)
        used += len(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_READY = re.compile(r"^\W*ready\b", re.IGNORECASE)
_SEARCH = re.compile(r"^\W*search\s*[:\-]\s*(.+)$", re.IGNORECASE)

# Some responses arrive as a bare query with no verb at all — the model drops
# the "SEARCH:" prefix and just states what it wants to look up. Accepting
# those is worth a little machinery, but the acceptance has to be strict in a
# specific direction.
#
# Both mistakes are recoverable, but they are not equally bad. Rejecting a real
# bare query stops the loop early, which is recorded as UNPARSEABLE_DECISION
# and understates C4. Accepting a sentence of the model's reasoning as a query
# spends a retrieval on nonsense *and writes that nonsense into
# `rewritten_queries`*, where Chapter 4 reads it as evidence of what the agent
# decided to do. A log that misreports the agent's reasoning is worse than a
# log that admits it could not read it, so this errs towards rejection.
_MAX_BARE_QUERY_WORDS = 12

_PROSE_MARKERS = frozenset(
    {
        # First and second person: a query has no speaker.
        "i",
        "me",
        "my",
        "we",
        "us",
        "our",
        "you",
        "your",
        # Hedging and self-description: the model talking about its own state.
        "think",
        "thinks",
        "believe",
        "sure",
        "unsure",
        "seems",
        "seem",
        "appears",
        "perhaps",
        "maybe",
        "unclear",
        "sufficient",
        "insufficient",
        "enough",
        "need",
        "needs",
        "want",
        "should",
        "would",
        "could",
        "cannot",
        "not",
        "no",
        "none",
        "nothing",
        "please",
        "sorry",
        "however",
    }
)


def parse_decision(text: str) -> Decision:
    """Read the model's one-line answer.

    Tolerant of the wrappers a chat model adds — markdown bold, a leading
    "Answer:", a trailing full stop, an explanatory sentence before the line —
    but never lenient about the outcome. Anything it cannot read becomes
    `parsed=False`, which stops the loop and is recorded, rather than being
    quietly treated as READY.
    """
    raw = (text or "").strip()
    if not raw:
        return Decision(ready=True, parsed=False, raw=raw)

    for line in _candidate_lines(raw):
        if _READY.match(line):
            return Decision(ready=True, raw=raw)

        match = _SEARCH.match(line)
        if match:
            query = _clean_query(match.group(1))
            if not query:
                # "SEARCH:" with nothing after it is not a usable instruction.
                return Decision(ready=True, parsed=False, raw=raw)
            return Decision(ready=False, query=query, raw=raw)

    bare = _bare_query(raw)
    if bare:
        return Decision(ready=False, query=bare, raw=raw)

    return Decision(ready=True, parsed=False, raw=raw)


def _candidate_lines(raw: str) -> list[str]:
    """Lines worth testing, stripped of markdown and common lead-ins."""
    lines: list[str] = []
    for line in raw.splitlines():
        cleaned = line.strip().strip("*_` ").strip()
        cleaned = re.sub(
            r"^(answer|decision|response)\s*[:\-]\s*", "", cleaned, flags=re.I
        )
        if cleaned:
            lines.append(cleaned)
    return lines


def _clean_query(value: str) -> str:
    query = value.strip().strip("\"'`*_ ").rstrip(".").strip()
    # A model sometimes appends its reasoning after the query on the same line.
    query = query.split(" because ")[0].split(" so that ")[0]
    return " ".join(query.split())


def _bare_query(raw: str) -> str | None:
    """Accept a single short line that is plainly a query, not commentary.

    A query is a noun phrase or a wh-question. A refusal, an apology or a
    statement about what the excerpts contain is a sentence, and sentences of
    that kind carry tells: a speaker ("I", "you"), a hedge ("perhaps",
    "unclear"), a negation ("not", "none"), or sentence-internal punctuation.
    Any tell rejects the line, which is why the check is a filter over tokens
    rather than a list of opening phrases — the model has many more ways to
    begin an apology than can be enumerated.
    """
    lines = _candidate_lines(raw)
    if len(lines) != 1:
        return None

    line = _clean_query(lines[0])
    words = line.split()
    if not (2 <= len(words) <= _MAX_BARE_QUERY_WORDS):
        return None

    # Clause punctuation belongs to prose, not to a search query.
    if any(mark in line for mark in (",", ";", ":", "—")):
        return None

    tokens = {word.strip(".,;:!?\"'()").lower() for word in words}
    if tokens & _PROSE_MARKERS:
        return None

    # What survives is a wh-question or a bare noun phrase — either is usable
    # as a search query.
    return line


__all__ = [
    "DECIDE_SYSTEM",
    "MAX_CONTEXT_CHARS",
    "Decision",
    "build_decide_prompt",
    "parse_decision",
]
