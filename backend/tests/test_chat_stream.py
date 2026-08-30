"""Phase 6: the chat endpoint's wire format and its guardrails.

No database, no Ollama, no Chroma. The RAG service is replaced with a fake
event stream, because what is under test here is the transport: does an event
reach a browser in a form it can parse, and are the two things that must not
leak — an unevaluated configuration, and a silently truncated stream — actually
prevented.

`rag/tests/test_streaming.py` covers what the events *contain*.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from app.api.routes import chat
from app.main import app
from app.services import rag_service


class _Event:
    def __init__(self, name: str, data: dict) -> None:
        self.name = name
        self.data = data


def _fake_stream(events: list[_Event]):
    async def stream(question: str, config_name: str) -> AsyncIterator[_Event]:
        for event in events:
            yield event

    return stream


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    """Parse the response the way a browser's EventSource would."""
    out: list[tuple[str, dict]] = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        name = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        assert name is not None, f"event block without a type: {block!r}"
        out.append((name, data))
    return out


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestTheWireFormat:
    def test_events_parse_as_a_browser_would_parse_them(
        self, client: TestClient, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            chat,
            "answer_stream",
            _fake_stream(
                [
                    _Event("stage", {"stage": "retrieval", "status": "started"}),
                    _Event("token", {"text": "The intake "}),
                    _Event("token", {"text": "is 180."}),
                    _Event("answer", {"answer": "The intake is 180."}),
                    _Event("done", {"latency_ms": 1.0}),
                ]
            ),
        )
        response = client.post("/api/v1/chat", json={"question": "intake?"})

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        # Without this, a proxy buffers the whole answer and the streaming is
        # invisible to the user — the failure looks like a hang, not a bug.
        assert response.headers["x-accel-buffering"] == "no"

        events = _parse_sse(response.text)
        assert [name for name, _ in events] == ["stage", "token", "token", "answer", "done"]
        assert events[-2][1]["answer"] == "The intake is 180."

    def test_a_newline_in_the_payload_cannot_split_an_event(
        self, client: TestClient, monkeypatch
    ) -> None:
        """SSE is newline-delimited, so an unescaped newline in an answer
        would truncate the event and hand the client half a JSON document."""
        monkeypatch.setattr(
            chat,
            "answer_stream",
            _fake_stream(
                [
                    _Event("answer", {"answer": "Line one.\nLine two.\n\nLine three."}),
                ]
            ),
        )
        response = client.post("/api/v1/chat", json={"question": "multi line?"})

        events = _parse_sse(response.text)
        assert len(events) == 1
        assert events[0][1]["answer"] == "Line one.\nLine two.\n\nLine three."


class TestFailureIsReported:
    def test_a_mid_stream_failure_becomes_an_error_event(
        self, client: TestClient, monkeypatch
    ) -> None:
        """The status line has already gone out, so a 500 is impossible.

        A truncated stream is indistinguishable from a completed one, so the
        only honest option left is to say so in-band.
        """

        async def exploding(question: str, config_name: str):
            yield _Event("stage", {"stage": "retrieval", "status": "started"})
            raise RuntimeError("ollama is down")

        monkeypatch.setattr(chat, "answer_stream", exploding)
        response = client.post("/api/v1/chat", json={"question": "anything?"})

        assert response.status_code == 200
        events = _parse_sse(response.text)
        assert events[-1][0] == "error"
        assert "ollama is down" in events[-1][1]["message"]


class TestOnlyEvaluatedConfigurationsAreServed:
    """The portal is not a research console.

    Letting a visitor select any of C0–C5 would put configurations nobody
    evaluated — and in C0's case one built deliberately to be naive — in front
    of the public.
    """

    def test_an_unknown_configuration_is_refused(self, client: TestClient) -> None:
        response = client.post("/api/v1/chat", json={"question": "intake?", "config": "C9"})
        assert response.status_code == 400
        assert "C9" in response.json()["detail"]

    def test_the_naive_baseline_is_not_offered(self, client: TestClient) -> None:
        response = client.post("/api/v1/chat", json={"question": "intake?", "config": "C0"})
        assert response.status_code == 400

    @pytest.mark.parametrize("name", ["C3", "c3", " C5 "])
    def test_offered_configurations_are_accepted_case_insensitively(self, name: str) -> None:
        assert rag_service.resolve_config(name) in rag_service.PORTAL_CONFIGS

    def test_no_configuration_means_the_default(self) -> None:
        assert rag_service.resolve_config(None) == rag_service.DEFAULT_CONFIG
        assert rag_service.DEFAULT_CONFIG == "C3"

    def test_the_configs_endpoint_lists_exactly_what_is_servable(self, client: TestClient) -> None:
        body = client.get("/api/v1/chat/configs").json()
        assert body["default"] == rag_service.DEFAULT_CONFIG
        assert {c["name"] for c in body["configs"]} == set(rag_service.PORTAL_CONFIGS)


class TestTheRequestIsValidated:
    @pytest.mark.parametrize("question", ["", "  ", "ab"])
    def test_a_too_short_question_is_rejected(self, client: TestClient, question: str) -> None:
        response = client.post("/api/v1/chat", json={"question": question})
        assert response.status_code == 422

    def test_an_overlong_question_is_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/chat", json={"question": "x" * (chat.MAX_QUESTION_CHARS + 1)}
        )
        assert response.status_code == 422
