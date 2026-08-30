"""The API's single point of contact with the knowledge service.

Two problems this module exists to solve, both consequences of measured
behaviour rather than of taste.

**Building a pipeline is expensive and must happen once.** It loads the
embedding model and, for C3 and later, the cross-encoder. Constructing one per
request would add seconds to every question and multiply memory on a machine
that is already tight. So pipelines are cached per configuration and built on
first use.

**Answering blocks for minutes.** `Pipeline.ask()` is synchronous and takes
between 60 and 330 seconds depending on configuration. Calling it from an async
route would stall the event loop and freeze every other request in the process.
So the generator runs in a worker thread and its events cross into async code
through a queue.

The set of configurations the portal will serve is deliberately narrow. C3 is
the default because the evaluation showed C4's extra ~95 seconds changes the
retrieved evidence on 2 questions in 20; C5 is offered explicitly, for a user
who asks for the answer to be checked.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import AsyncIterator
from typing import Any

import anyio
from app.core.logging import get_logger

logger = get_logger(__name__)

# What a client may ask for, and what each means in plain language. Anything
# else is refused: the portal is not a research console, and letting arbitrary
# configuration names through would let a user select a pipeline nobody has
# evaluated.
PORTAL_CONFIGS: dict[str, str] = {
    "C3": "Standard — hybrid retrieval with cross-encoder reranking",
    "C5": "Verified — adds iterative retrieval and answer verification",
}
DEFAULT_CONFIG = "C3"

_pipelines: dict[str, Any] = {}
_lock = threading.Lock()

_SENTINEL = object()


def resolve_config(name: str | None) -> str:
    """Validate a requested configuration, or fall back to the default."""
    if not name:
        return DEFAULT_CONFIG
    key = name.strip().upper()
    if key not in PORTAL_CONFIGS:
        raise ValueError(
            f"unknown configuration {name!r}. Available: {', '.join(sorted(PORTAL_CONFIGS))}"
        )
    return key


def get_pipeline(config_name: str) -> Any:
    """Return the cached pipeline for a configuration, building it if needed.

    Double-checked under a lock: two simultaneous first requests would
    otherwise each load an embedding model, which on this hardware is a
    multi-second, multi-hundred-megabyte mistake.
    """
    pipeline = _pipelines.get(config_name)
    if pipeline is not None:
        return pipeline

    with _lock:
        pipeline = _pipelines.get(config_name)
        if pipeline is None:
            from rag.config import get_config
            from rag.factory import build_pipeline

            logger.info("building_pipeline", config=config_name)
            pipeline = build_pipeline(get_config(config_name))
            _pipelines[config_name] = pipeline
    return pipeline


async def answer_stream(question: str, config_name: str) -> AsyncIterator[Any]:
    """Yield `rag.streaming.Event`s from a worker thread, without blocking.

    The pipeline is synchronous and slow. Rather than wrap each stage in an
    async shim — which would mean a second implementation of the answering path
    and the drift that comes with it — the whole generator runs on a thread and
    pushes events into a queue this coroutine drains.

    The queue is bounded. If a client stops reading, the producer blocks on a
    full queue rather than accumulating an unbounded answer in memory.
    """
    from rag.streaming import answer_events

    pipeline = get_pipeline(config_name)
    events: queue.Queue[Any] = queue.Queue(maxsize=64)

    def produce() -> None:
        try:
            for event in answer_events(pipeline, question):
                events.put(event)
        except Exception as exc:  # noqa: BLE001 - reported to the client below
            logger.exception("answer_failed", config=config_name)
            events.put(exc)
        finally:
            events.put(_SENTINEL)

    thread = threading.Thread(target=produce, name="rag-answer", daemon=True)
    thread.start()

    while True:
        item = await anyio.to_thread.run_sync(events.get)
        if item is _SENTINEL:
            break
        if isinstance(item, Exception):
            raise item
        yield item


__all__ = [
    "DEFAULT_CONFIG",
    "PORTAL_CONFIGS",
    "answer_stream",
    "get_pipeline",
    "resolve_config",
]
