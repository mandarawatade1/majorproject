"""What a verification pass produces, and the protocol that produces it.

C5's claim is narrow and worth stating precisely: it does not make answers
better, it makes unsupported answers *visible*, and refuses the worst of them.
Everything here is therefore built around recording a judgment rather than
around changing text — the one place text changes (a total refusal) is a single
flag that the pipeline acts on, not something a verifier does on its own.

Kept free of any model or network dependency so the whole decision surface —
what counts as unsupported, when a refusal fires, what a malformed verdict does
— is testable without Ollama.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from rag.generation.prompts import AssembledContext


class Verdict(StrEnum):
    """The outcome of one verification pass.

    `SKIPPED` and `UNPARSEABLE` are deliberately distinct from `UNSUPPORTED`.
    An answer nobody could check and an answer checked and found baseless are
    different results, and averaging them together would let a broken verifier
    masquerade as a hallucinating generator.
    """

    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    SKIPPED = "skipped"
    UNPARSEABLE = "unparseable"


@dataclass(slots=True)
class VerificationResult:
    """One verification pass, recorded whole.

    `original_answer` is kept even when a refusal replaces the text. Discarding
    what the generator actually said would make the refusal unauditable — a
    reader could not tell whether C5 suppressed a hallucination or destroyed a
    good answer, which is precisely the question a refusal invites.
    """

    verdict: Verdict = Verdict.SKIPPED
    sentences: int = 0
    checked: int = 0
    unsupported: list[int] = field(default_factory=list)
    unsupported_text: list[str] = field(default_factory=list)
    refused: bool = False
    original_answer: str = ""
    raw: str = ""
    latency_ms: float = 0.0

    @property
    def supported(self) -> int:
        return max(self.checked - len(self.unsupported), 0)

    @property
    def support_rate(self) -> float | None:
        """Share of checked sentences the verifier accepted.

        None rather than 1.0 when nothing was checked. A skipped verification
        is not a perfect score, and a mean over `None`s that were silently read
        as 1.0 would report a system as fully grounded precisely when it was
        never examined.
        """
        if self.checked == 0:
            return None
        return self.supported / self.checked

    def to_log(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "sentences": self.sentences,
            "checked": self.checked,
            "supported": self.supported,
            "unsupported": self.unsupported,
            "support_rate": (
                round(self.support_rate, 4) if self.support_rate is not None else None
            ),
            "refused": self.refused,
            "raw": self.raw[:200],
            "latency_ms": round(self.latency_ms, 1),
        }


class Verifier(Protocol):
    """Checks a generated answer against the context it was given.

    One method, matching the shape of `Chunker`, `Retriever` and `Generator`,
    so the pipeline holds a verifier or holds nothing and the difference is one
    branch.
    """

    name: str

    def verify(
        self, question: str, answer: str, context: AssembledContext
    ) -> VerificationResult: ...


__all__ = ["VerificationResult", "Verdict", "Verifier"]
