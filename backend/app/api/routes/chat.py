"""Ask PCE — the chat endpoint, as Server-Sent Events.

Why SSE rather than a plain JSON response: on the evaluation hardware an answer
takes between 60 and 330 seconds, and under the agentic configurations roughly
100 of those pass in retrieval, before the first token exists. A blocking
request would hit proxy and browser timeouts and would show the user nothing
until it finished. SSE lets the server say what it is doing — searching,
re-searching, reranking, verifying — and then stream the answer.

Why not WebSockets: the traffic is one-directional and short-lived. SSE is a
plain HTTP response, so it needs no separate upgrade path, reconnects on its
own, and works through the same middleware and logging as every other route.

The client contract is documented on `rag.streaming.answer_events`. One rule
matters above the rest, and it is repeated here because getting it wrong would
undo C5: **the `answer` event is authoritative, the `token` events are a
preview.** Verification can withhold an answer the client has already rendered.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from app.core.logging import get_logger
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.rag_service import (
    DEFAULT_CONFIG,
    PORTAL_CONFIGS,
    answer_stream,
    resolve_config,
)

logger = get_logger(__name__)
router = APIRouter(tags=["chat"])

MAX_QUESTION_CHARS = 500


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=MAX_QUESTION_CHARS)
    config: str | None = Field(
        default=None,
        description=(
            "Pipeline configuration. "
            f"One of {sorted(PORTAL_CONFIGS)}; defaults to {DEFAULT_CONFIG}."
        ),
    )


def _sse(name: str, data: dict) -> str:
    """One Server-Sent Event.

    `json.dumps` with no newlines in the payload: SSE is newline-delimited, so
    a raw newline inside `data:` would truncate the event. Compact separators
    keep the stream small over a slow connection.
    """
    body = json.dumps(data, separators=(",", ":"), default=str)
    return f"event: {name}\ndata: {body}\n\n"


@router.get("/chat/configs", summary="Configurations this portal will answer with")
def list_configs() -> dict:
    """Deliberately not the full C0–C5 list.

    The portal serves the two configurations the evaluation supports offering:
    C3 as the default, C5 when a user wants the answer checked. The rest exist
    for the ablation, not for visitors.
    """
    return {
        "default": DEFAULT_CONFIG,
        "configs": [
            {"name": name, "description": description}
            for name, description in sorted(PORTAL_CONFIGS.items())
        ],
    }


@router.post("/chat", summary="Ask a question, streamed as Server-Sent Events")
async def ask(request: AskRequest) -> StreamingResponse:
    try:
        config_name = resolve_config(request.config)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    question = request.question.strip()
    logger.info("chat_question", config=config_name, chars=len(question))

    async def stream() -> AsyncIterator[str]:
        try:
            async for event in answer_stream(question, config_name):
                yield _sse(event.name, event.data)
        except Exception as exc:  # noqa: BLE001
            # The response has already begun, so a 500 is no longer available:
            # the status line went out with the first event. An `error` event
            # is the only way to tell a client something went wrong, and
            # sending one is better than a silently truncated stream that a
            # client cannot distinguish from a completed answer.
            logger.exception("chat_stream_failed", config=config_name)
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Nginx buffers proxied responses by default, which would hold
            # every event until the answer finished and defeat the point.
            "X-Accel-Buffering": "no",
        },
    )
