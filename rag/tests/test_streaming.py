"""Phase 6: the event stream behind the portal's chat.

The property that matters most here is not the wire format — it is that a
streamed answer is the *same* answer `ask()` produces. If the portal retrieved
or prompted even slightly differently, the answers users see would not be the
answers Chapter 4 measured, and the evaluation would describe a system nobody
used. Several tests below exist only to pin that.

Everything runs with the deterministic embedder and an in-memory index: no
Ollama, no Chroma, no torch.
"""

from __future__ import annotations

import tempfile
from pathlib import Path


from rag.chunking import FixedSizeChunker
from rag.config import C0_BASELINE, C5_FULL, RetrievalStrategy
from rag.embedding import DeterministicEmbedder
from rag.generation.base import GenerationResult, StreamingGenerator
from rag.indexing import InMemoryIndex
from rag.indexing.bm25 import BM25Index
from rag.ingestion.models import DocumentCategory, ParsedDocument, SourceType
from rag.pipeline import Pipeline
from rag.retrieval.base import RetrievalResult
from rag.streaming import Event, answer_events

# ---------------------------------------------------------------------------


class _BlockingGenerator:
    """Satisfies `Generator` only — no streaming."""

    model_name = "fake"

    def __init__(self, answer: str = "The intake is 180 students [S1].") -> None:
        self.answer = answer
        self.calls: list[tuple[str, str | None]] = []

    def generate(self, prompt: str, system: str | None = None) -> GenerationResult:
        self.calls.append((prompt, system))
        return GenerationResult(
            answer=self.answer, model_name=self.model_name, latency_ms=1.0
        )


class _StreamingFake(_BlockingGenerator):
    """Satisfies `StreamingGenerator`: fragments, then the final result."""

    def stream(self, prompt: str, system: str | None = None):
        self.calls.append((prompt, system))
        for word in self.answer.split(" "):
            yield word + " "
        yield GenerationResult(
            answer=self.answer, model_name=self.model_name, latency_ms=1.0
        )


def _document(doc_id: str, text: str) -> ParsedDocument:
    return ParsedDocument(
        doc_id=doc_id,
        title=doc_id.replace("-", " ").title(),
        source_type=SourceType.WEB_HTML,
        category=DocumentCategory.PROGRAMME,
        text=text,
        source_url=f"https://www.pce.ac.in/{doc_id}",
    )


def _pipeline(generator, config=C0_BASELINE) -> Pipeline:
    # Hybrid configurations need a sparse index; a temporary one keeps the
    # test off the repo's real BM25 pickle.
    sparse = None
    if config.uses_sparse:
        sparse = BM25Index(path=str(Path(tempfile.mkdtemp()) / "bm25.pkl"))

    pipeline = Pipeline(
        config,
        DeterministicEmbedder(),
        InMemoryIndex(),
        generator,
        sparse_index=sparse,
    )
    pipeline.chunker = FixedSizeChunker(size=200, overlap=20)
    pipeline.index_documents(
        [
            _document("courses-intake", "Computer Engineering intake is 180. " * 8),
            _document("about", "Pillai College of Engineering, New Panvel. " * 8),
        ]
    )
    return pipeline


# C5's verification, without C5's agent or reranker. LangGraph and torch are
# not installable in this environment, and neither is what these tests are
# about: the streaming layer's handling of a verification result. Keeping the
# name "C5" satisfies `implemented_configs()`; the overrides strip the stages
# this file has no business exercising.
VERIFY_ONLY = C5_FULL.with_overrides(
    agentic=False,
    rerank=False,
    retrieval=RetrievalStrategy.DENSE,
    dense_top_k=5,
    sparse_top_k=0,
)


def _collect(pipeline, question: str = "What is the intake?") -> list[Event]:
    return list(answer_events(pipeline, question))


def _names(events: list[Event]) -> list[str]:
    return [e.name for e in events]


# ---------------------------------------------------------------------------


class TestTheEventSequence:
    def test_the_documented_order_holds(self) -> None:
        events = _collect(_pipeline(_StreamingFake()))
        names = _names(events)

        assert names[0] == "stage"
        assert names[-1] == "done"
        assert names[-2] == "answer"
        # Sources arrive before any token, so a citation marker in the streamed
        # text resolves the moment it appears.
        assert names.index("sources") < names.index("token")

    def test_every_event_is_json_serialisable(self) -> None:
        """The transport layer will serialise these; a dataclass or an enum
        leaking into `data` would fail at runtime in the route, not here."""
        import json

        for event in _collect(_pipeline(_StreamingFake())):
            json.dumps(event.data)

    def test_sources_carry_what_a_citation_needs(self) -> None:
        events = _collect(_pipeline(_StreamingFake()))
        sources = next(e for e in events if e.name == "sources")
        assert sources.data["sources"], "no sources emitted"
        first = sources.data["sources"][0]
        assert first["marker"] == "[S1]"
        assert first["label"]
        assert "is_demo" in first
        assert "chunk_id" in first

    def test_retrieval_stage_reports_what_it_found(self) -> None:
        events = _collect(_pipeline(_StreamingFake()))
        finished = next(
            e
            for e in events
            if e.name == "stage"
            and e.data.get("stage") == "retrieval"
            and e.data.get("status") == "finished"
        )
        assert finished.data["passages"] > 0
        assert finished.data["elapsed_ms"] >= 0


class TestStreamingMatchesAsking:
    """The portal must not become a second, divergent implementation."""

    def test_the_streamed_answer_equals_the_asked_answer(self) -> None:
        pipeline = _pipeline(_StreamingFake())
        asked = pipeline.ask("What is the intake?")
        events = _collect(pipeline)
        answer = next(e for e in events if e.name == "answer")
        assert answer.data["answer"] == asked.answer

    def test_both_paths_build_the_identical_prompt(self) -> None:
        """The strongest form of the guarantee.

        Same retrieval, same context, same prompt — so a portal answer is the
        answer the evaluation measured, not a lookalike.
        """
        generator = _StreamingFake()
        pipeline = _pipeline(generator)

        pipeline.ask("What is the intake?")
        asked_prompt, asked_system = generator.calls[-1]

        _collect(pipeline)
        streamed_prompt, streamed_system = generator.calls[-1]

        assert streamed_prompt == asked_prompt
        assert streamed_system == asked_system

    def test_tokens_concatenate_to_the_answer(self) -> None:
        events = _collect(_pipeline(_StreamingFake()))
        streamed = "".join(e.data["text"] for e in events if e.name == "token").strip()
        answer = next(e for e in events if e.name == "answer")
        assert streamed == answer.data["answer"]


class TestTheNonStreamingFallback:
    """A client written against this stream must work either way."""

    def test_a_blocking_generator_still_produces_the_full_sequence(self) -> None:
        streaming = _names(_collect(_pipeline(_StreamingFake())))
        blocking = _names(_collect(_pipeline(_BlockingGenerator())))

        # Identical but for how many token events the answer arrived in.
        assert [n for n in streaming if n != "token"] == [
            n for n in blocking if n != "token"
        ]
        assert blocking.count("token") == 1

    def test_the_protocol_check_distinguishes_them(self) -> None:
        assert isinstance(_StreamingFake(), StreamingGenerator)
        assert not hasattr(_BlockingGenerator(), "stream")


class TestVerificationInTheStream:
    def test_c5_reports_its_verdict_as_a_stage(self) -> None:
        pipeline = _pipeline(_StreamingFake(), config=VERIFY_ONLY)
        pipeline.generator.answer = "The intake is 180 students [S1]."
        events = _collect(pipeline)

        verification = [
            e
            for e in events
            if e.name == "stage" and e.data.get("stage") == "verification"
        ]
        assert len(verification) == 2  # started, finished
        assert "verdict" in verification[-1].data

    def test_earlier_configurations_emit_no_verification_stage(self) -> None:
        events = _collect(_pipeline(_StreamingFake()))
        assert not [
            e
            for e in events
            if e.name == "stage" and e.data.get("stage") == "verification"
        ]
        answer = next(e for e in events if e.name == "answer")
        assert "verification" not in answer.data

    def test_a_refusal_supersedes_the_tokens_already_streamed(self) -> None:
        """The one case where the final answer contradicts the preview.

        C5 can replace an answer the client has already rendered token by
        token. The `answer` event is therefore authoritative and the tokens are
        a preview — a client that displays its own accumulation would show text
        the system decided to withhold, which is the opposite of what C5 is
        for. The withheld text is carried too, so the UI can be honest about
        what happened rather than silently blanking.
        """

        class _AlwaysUnsupported(_StreamingFake):
            def generate(self, prompt: str, system: str | None = None):
                # The verifier's call: reject every claim.
                return GenerationResult(
                    answer="UNSUPPORTED: 1", model_name=self.model_name
                )

        pipeline = _pipeline(_AlwaysUnsupported(), config=VERIFY_ONLY)
        events = _collect(pipeline)

        answer = next(e for e in events if e.name == "answer")
        streamed = "".join(e.data["text"] for e in events if e.name == "token").strip()

        assert answer.data["verification"]["refused"] is True
        assert answer.data["answer"] != streamed
        assert answer.data["verification"]["withheld_text"] == streamed


class TestTheAgentIsVisible:
    """C4's rounds become progress a user can watch.

    Driven by a scripted `RetrievalResult` rather than a real agentic
    pipeline: LangGraph is not installable here, and the behaviour under test
    belongs to the streaming layer, not the graph. `rag/tests/test_agentic.py`
    covers how those iteration records are produced.
    """

    def _with_iterations(self, pipeline: Pipeline) -> Pipeline:
        inner = pipeline.retriever

        class _Scripted:
            name = "scripted"

            def retrieve(self, query: str, top_k: int) -> RetrievalResult:
                result = inner.retrieve(query, top_k)
                result.iterations = [
                    {
                        "iteration": 1,
                        "query": query,
                        "hits_returned": 20,
                        "new_chunks": 20,
                        "decision": "SEARCH: intake 2023",
                    },
                    {
                        "iteration": 2,
                        "query": "intake 2023",
                        "hits_returned": 20,
                        "new_chunks": 11,
                        "decision": "READY",
                    },
                ]
                result.stop_reason = "model_says_ready"
                result.iteration_count = 2
                return result

        pipeline.retriever = _Scripted()
        return pipeline

    def test_each_round_is_reported_as_it_was_recorded(self) -> None:
        """The answer to C4's worst property.

        On this hardware the agent spends ~95 s before the first token exists.
        Reporting each round turns a minute and a half of dead air into
        something legible.
        """
        pipeline = self._with_iterations(_pipeline(_StreamingFake()))
        events = _collect(pipeline)

        agent = [
            e for e in events if e.name == "stage" and e.data.get("stage") == "agent"
        ]
        rounds = [e for e in agent if "iteration" in e.data]
        assert [e.data["iteration"] for e in rounds] == [1, 2]
        assert rounds[1].data["new_passages"] == 11
        assert rounds[0].data["query"]
        assert any(e.data.get("stop_reason") == "model_says_ready" for e in agent)

    def test_agent_rounds_precede_the_first_token(self) -> None:
        """Otherwise they would be progress reported after the wait, which is
        no use to anyone."""
        pipeline = self._with_iterations(_pipeline(_StreamingFake()))
        names = _names(_collect(pipeline))
        first_agent = next(
            i
            for i, e in enumerate(_collect(pipeline))
            if e.name == "stage" and e.data.get("stage") == "agent"
        )
        assert first_agent < names.index("token")

    def test_non_agentic_configurations_emit_no_agent_stage(self) -> None:
        events = _collect(_pipeline(_StreamingFake()))
        assert not [
            e for e in events if e.name == "stage" and e.data.get("stage") == "agent"
        ]
