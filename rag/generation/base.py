"""The generation protocol and its result."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class GenerationResult:
    answer: str
    model_name: str
    latency_ms: float = 0.0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int | None:
        if self.prompt_tokens is None or self.completion_tokens is None:
            return None
        return self.prompt_tokens + self.completion_tokens


class Generator(Protocol):
    model_name: str

    def generate(self, prompt: str, system: str | None = None) -> GenerationResult: ...


@runtime_checkable
class StreamingGenerator(Protocol):
    """A generator that can also yield tokens as they arrive.

    Kept separate from `Generator` rather than added to it. Every stage of the
    pipeline and every test double satisfies `Generator`; requiring all of them
    to grow a streaming method to serve one API route would be the tail wagging
    the dog. `runtime_checkable` lets a caller ask whether streaming is
    available and fall back to `generate()` when it is not.
    """

    model_name: str

    def generate(self, prompt: str, system: str | None = None) -> GenerationResult: ...

    def stream(
        self, prompt: str, system: str | None = None
    ) -> Iterator[str | GenerationResult]:
        """Yield answer text as it arrives, then one final `GenerationResult`.

        The trailing result carries the token counts and latency that only
        exist once generation has finished, so a caller gets the same record
        `generate()` would have returned without buffering the answer twice.
        """
        ...
