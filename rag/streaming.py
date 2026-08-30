"""Answering as a sequence of events, for the portal.

`Pipeline.ask()` returns an answer after between 60 and 330 seconds depending
on the configuration, and on the measured hardware most of that is spent before
the first token exists: under C4 and C5, retrieval alone averages 95-105 s.
Token streaming on its own would therefore leave a user watching nothing at all
for the first minute and a half, which reads as a hung page rather than a
thinking one.

So this yields *stage* events too. What the agent is doing is genuinely
interesting -- it searched again, it found eleven new passages, it decided it
had enough -- and surfacing it turns the system's biggest weakness, its
latency, into the thing that makes it legible.

The design rule this module follows: **it never re-implements a pipeline
stage.** It calls `Pipeline.prepare()` and `Pipeline.finish()`, the same
methods `ask()` uses. If the portal assembled context or built prompts of its
own, portal answers would drift from the answers Chapter 4 measured, and the
evaluation would describe a system nobody used.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from rag.generation.base import GenerationResult, StreamingGenerator
from rag.pipeline import Answer, Pipeline


@dataclass(slots=True)
class Event:
    """One thing worth telling the client about.

    `name` is the SSE event type; `data` is JSON-serialisable. Deliberately a
    plain record rather than a formatted SSE string, so the transport layer
    owns the wire format and this module stays testable without HTTP.
    """

    name: str
    data: dict[str, Any] = field(default_factory=dict)


def answer_events(pipeline: Pipeline, question: str) -> Iterator[Event]:
    """Answer a question as a stream of events.

    Order is fixed and a client may rely on it:

        stage(retrieval) -> [stage(agent) ...] -> stage(context)
        -> sources -> token* -> stage(verification)? -> answer -> done

    `answer` always arrives, and always carries the same text `ask()` would
    have returned -- including a C5 refusal, which replaces text the client has
    already been shown token by token. That is why `answer` is authoritative
    and the tokens are a preview: a client must render the final text, not its
    accumulation of tokens.
    """
    started = time.perf_counter()

    yield Event(
        "stage",
        {"stage": "retrieval", "status": "started", "config": pipeline.config.name},
    )

    prepared = pipeline.prepare(question)
    retrieval = prepared.retrieval

    # The agent's round-by-round record, if this configuration has one. This is
    # the part worth watching: it is the only place a user can see the system
    # decide something.
    for iteration in retrieval.iterations:
        yield Event(
            "stage",
            {
                "stage": "agent",
                "iteration": iteration.get("iteration"),
                "query": iteration.get("query"),
                "new_passages": iteration.get("new_chunks"),
                "decision": iteration.get("decision"),
            },
        )
    if retrieval.stop_reason:
        yield Event(
            "stage",
            {
                "stage": "agent",
                "status": "finished",
                "stop_reason": retrieval.stop_reason,
            },
        )

    yield Event(
        "stage",
        {
            "stage": "retrieval",
            "status": "finished",
            "passages": len(retrieval.hits),
            "reranked_to": len(retrieval.reranked_hits) or None,
            "elapsed_ms": round(prepared.retrieval_ms, 1),
        },
    )

    # Sources before tokens, so citation markers in the streamed text resolve
    # to something the moment they appear.
    yield Event(
        "sources",
        {
            "sources": [
                {
                    "marker": f"[S{position}]",
                    "label": hit.citation_label(),
                    "url": hit.metadata.get("source_url") or None,
                    "page": hit.page_number,
                    "is_demo": hit.is_demo,
                    "chunk_id": hit.chunk_id,
                }
                for position, hit in enumerate(prepared.context.sources, start=1)
            ],
            "contains_demo": prepared.context.contains_demo,
        },
    )

    yield Event("stage", {"stage": "generation", "status": "started"})

    generated = yield from _generate(pipeline, prepared)

    if pipeline.verifier is not None:
        yield Event("stage", {"stage": "verification", "status": "started"})

    answer = pipeline.finish(prepared, generated, started)

    if answer.verification is not None:
        v = answer.verification
        yield Event(
            "stage",
            {
                "stage": "verification",
                "status": "finished",
                "verdict": v.verdict.value,
                "checked": v.checked,
                "unsupported": v.unsupported,
                "support_rate": v.support_rate,
                "refused": v.refused,
            },
        )

    yield Event("answer", _answer_payload(answer))
    yield Event("done", {"latency_ms": round(answer.latency_ms, 1)})


def _generate(pipeline: Pipeline, prepared: Any) -> Iterator[Event]:
    """Stream tokens if the generator can, otherwise produce them in one go.

    The fallback matters: it keeps every event before and after generation
    identical whether or not streaming is available, so a client written
    against this stream works with a non-streaming generator (a test double, a
    future backend) without a second code path.
    """
    generator = pipeline.generator
    if isinstance(generator, StreamingGenerator) and hasattr(generator, "stream"):
        result: GenerationResult | None = None
        for piece in generator.stream(prepared.prompt, system=prepared.system):
            if isinstance(piece, GenerationResult):
                result = piece
            else:
                yield Event("token", {"text": piece})
        if result is None:  # pragma: no cover - a stream that yielded no result
            raise RuntimeError("streaming generator produced no final result")
        return result

    result = generator.generate(prepared.prompt, system=prepared.system)
    yield Event("token", {"text": result.answer})
    return result


def _answer_payload(answer: Answer) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "answer": answer.answer,
        "config": answer.config_name,
        "model": answer.model_name,
        "used_demo_sources": answer.used_demo_sources,
        "latency_ms": round(answer.latency_ms, 1),
        "retrieval_ms": round(answer.retrieval_ms, 1),
        "generation_ms": round(answer.generation_ms, 1),
    }
    if answer.verification is not None:
        v = answer.verification
        payload["verification"] = {
            "verdict": v.verdict.value,
            "support_rate": v.support_rate,
            "unsupported_sentences": v.unsupported_text,
            "refused": v.refused,
            # What was withheld, so a refusal is auditable in the UI exactly as
            # it is on the command line. Suppressing text invisibly would make
            # C5 unfalsifiable to a reader.
            "withheld_text": v.original_answer if v.refused else None,
        }
    return payload


__all__ = ["Event", "answer_events"]
