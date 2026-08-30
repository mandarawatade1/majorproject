"""Phase 3: the C0 baseline.

Every test here runs with no torch, no Chroma, no Ollama and no model download,
using the deterministic embedder and an in-memory index. That matters: the
baseline is the reference point for every number in Chapter 4, so its behaviour
needs to be checkable in seconds on any machine rather than only on the one
with the models installed.
"""

from __future__ import annotations

import dataclasses

import pytest

from rag.chunking import FixedSizeChunker
from rag.config import (
    ABLATION_ORDER,
    C0_BASELINE,
    C1_CONTROL,
    C1_STRUCTURE_AWARE,
    C5_FULL,
    CONFIGURATIONS,
    get_config,
    implemented_configs,
)
from rag.embedding import DeterministicEmbedder
from rag.generation.base import GenerationResult
from rag.generation.prompts import (
    BASE_SYSTEM,
    GROUNDED_SYSTEM,
    assemble_context,
    build_prompt,
)
from rag.indexing import InMemoryIndex
from rag.indexing.base import IndexedHit
from rag.ingestion.models import DocumentCategory, ParsedDocument, SourceType
from rag.pipeline import Pipeline
from rag.retrieval import DenseRetriever


class _FakeGenerator:
    """Records what it was asked, so prompt assembly can be asserted."""

    model_name = "fake"

    def __init__(self) -> None:
        self.prompt: str | None = None
        self.system: str | None = None

    def generate(self, prompt: str, system: str | None = None) -> GenerationResult:
        self.prompt, self.system = prompt, system
        return GenerationResult(
            answer="answer", model_name=self.model_name, latency_ms=1.0
        )


def _document(doc_id: str, text: str, *, demo: bool = False) -> ParsedDocument:
    return ParsedDocument(
        doc_id=doc_id,
        title=doc_id.replace("-", " ").title(),
        source_type=SourceType.LOCAL_MARKDOWN if demo else SourceType.WEB_HTML,
        category=DocumentCategory.SOP if demo else DocumentCategory.PROGRAMME,
        text=text,
        source_url=None if demo else f"https://www.pce.ac.in/{doc_id}",
        local_path=f"corpus/demo/{doc_id}.md" if demo else None,
        is_demo=demo,
        demo_reason="Internal procedures are not published publicly." if demo else None,
    )


def _hit(
    chunk_id: str, content: str, *, demo: bool = False, page: int | None = None
) -> IndexedHit:
    return IndexedHit(
        chunk_id=chunk_id,
        content=content,
        score=0.5,
        metadata={
            "document_id": "d",
            "document_title": "Doc",
            "is_demo": demo,
            "page_number": page if page is not None else -1,
            "section_path": "",
        },
    )


# ---------------------------------------------------------------------------


class TestTheAblationIsSingleVariable:
    """Each configuration must add exactly one thing to the one before it.

    This is the property the whole Chapter 4 comparison rests on. If C2
    differed from C1 in two ways, a measured improvement could not be
    attributed to hybrid retrieval.
    """

    def test_c0_enables_none_of_the_innovations(self) -> None:
        assert C0_BASELINE.innovations_enabled == []

    def test_c5_enables_all_five(self) -> None:
        assert len(C5_FULL.innovations_enabled) == 5

    def test_each_step_adds_exactly_one_innovation(self) -> None:
        counts = [
            len(CONFIGURATIONS[name].innovations_enabled) for name in ABLATION_ORDER
        ]
        assert counts == [0, 1, 2, 3, 4, 5]

    def test_each_config_is_a_superset_of_its_predecessor(self) -> None:
        for previous, current in zip(ABLATION_ORDER, ABLATION_ORDER[1:], strict=False):
            before = set(CONFIGURATIONS[previous].innovations_enabled)
            after = set(CONFIGURATIONS[current].innovations_enabled)
            assert before < after, f"{current} does not strictly extend {previous}"

    def test_each_step_changes_exactly_the_fields_recorded_here(self) -> None:
        """The real check on the ablation — the one above only checks a label.

        `innovations_enabled` returns a curated list, so it reports "one
        innovation" no matter how many fields a configuration actually changes.
        It said C1 added one thing while C1 was in fact changing the chunker
        *and* the system prompt, and no test noticed for two phases.

        So this compares dataclass fields instead. Every delta below is written
        out deliberately: adding a field to a preset fails this test, and the
        fix is to justify the new entry here, not to widen the expectation.
        """
        expected = {
            # C1 changes two things. `enforce_citations` swaps BASE_SYSTEM for
            # GROUNDED_SYSTEM, so C0 -> C1 is chunking AND grounding. This is
            # what C1_CONTROL exists to separate; it is recorded here rather
            # than hidden.
            ("C0", "C1"): {"chunking", "enforce_citations"},
            # dense_top_k 5 -> 20 widens the pool RRF needs to fuse over. It
            # also means C2 assembles context from more chunks than C1 does —
            # a second effect of this step, and one Chapter 4 should name.
            ("C1", "C2"): {"retrieval", "dense_top_k", "sparse_top_k"},
            # Only the flag: rerank_top_n was already 5, so C3 narrows the
            # widened C2 pool back to the context size C1 had.
            ("C2", "C3"): {"rerank"},
            ("C3", "C4"): {"agentic"},
            # C5 checks the answer after generation; it changes nothing about
            # how the answer was produced, which is what keeps this last step
            # single-variable too.
            ("C4", "C5"): {"verify_answer"},
        }

        for previous, current in zip(ABLATION_ORDER, ABLATION_ORDER[1:], strict=False):
            before, after = CONFIGURATIONS[previous], CONFIGURATIONS[current]
            changed = {
                spec.name
                for spec in dataclasses.fields(before)
                if getattr(before, spec.name) != getattr(after, spec.name)
            } - {"name", "description"}
            assert changed == expected[(previous, current)], (
                f"{previous} -> {current} changes {sorted(changed)}, "
                f"not {sorted(expected[(previous, current)])}"
            )

    def test_the_control_isolates_the_prompt_from_the_chunker(self) -> None:
        """C1-CONTROL must differ from C1 in the prompt flag and nothing else.

        If it drifted, the two runs it exists to separate would stop being
        comparable and the control would be worse than useless — it would look
        like a measurement while measuring something else.
        """
        changed = {
            spec.name
            for spec in dataclasses.fields(C1_CONTROL)
            if getattr(C1_CONTROL, spec.name) != getattr(C1_STRUCTURE_AWARE, spec.name)
        } - {"name", "description"}
        assert changed == {"enforce_citations"}
        assert C1_CONTROL.enforce_citations is False
        assert C1_CONTROL.chunking is C1_STRUCTURE_AWARE.chunking

    def test_the_control_is_not_a_stage_of_the_system(self) -> None:
        assert "C1-CONTROL" not in ABLATION_ORDER
        assert get_config("c1-control") is C1_CONTROL

    def test_the_control_answers_with_c0s_prompt(self) -> None:
        """The point of the control, asserted where it can be seen."""
        context = assemble_context([_hit("a", "text")])
        control_system, _ = build_prompt(
            "q", context, enforce_citations=C1_CONTROL.enforce_citations
        )
        c1_system, _ = build_prompt(
            "q", context, enforce_citations=C1_STRUCTURE_AWARE.enforce_citations
        )
        assert control_system == BASE_SYSTEM
        assert c1_system == GROUNDED_SYSTEM

    def test_configs_are_frozen(self) -> None:
        """A run must not be able to mutate the config it is measured under."""
        with pytest.raises((AttributeError, TypeError)):
            C0_BASELINE.name = "tampered"  # type: ignore[misc]

    def test_lookup_is_case_insensitive_and_errors_helpfully(self) -> None:
        assert get_config("c0") is C0_BASELINE
        with pytest.raises(KeyError, match="unknown configuration"):
            get_config("C9")


class TestUnbuiltConfigsAreRefused:
    """Running C3 today and silently getting C0 would put a wrong number in
    the report under a right-looking label.

    The list below moves as each phase lands, and moving it is deliberately
    part of finishing a phase: `implemented_configs()` is the gate, and a gate
    nobody has to update is a gate that stops meaning anything. As of Phase 5
    everything through C4 is built and C5 is not.
    """

    def test_the_gate_matches_what_is_actually_built(self) -> None:
        assert implemented_configs() == [
            "C0",
            "C1",
            "C2",
            "C3",
            "C4",
            "C5",
            "C1-CONTROL",
        ]

    def test_every_declared_configuration_is_now_buildable(self) -> None:
        """Phase 6 closes the gate's remaining gap: nothing is declared but
        unbuilt. The gate stays because each phase had to move it deliberately,
        which is what stopped a half-built stage being measured under a
        finished name."""
        built = set(implemented_configs())
        assert set(ABLATION_ORDER) <= built

    def test_an_unknown_configuration_is_still_refused(self) -> None:
        """The gate must keep working now that nothing legitimate trips it."""
        unbuilt = C5_FULL.with_overrides(name="C9", description="not a real config")
        with pytest.raises(NotImplementedError, match="not built yet"):
            Pipeline(unbuilt, DeterministicEmbedder(), InMemoryIndex(), _FakeGenerator())


class TestFixedChunker:
    def test_overlap_carries_across_the_boundary(self) -> None:
        text = "".join(str(i % 10) for i in range(300))
        chunks = FixedSizeChunker(size=100, overlap=20).chunk(_document("d", text))
        assert (
            chunks[1].content[:20] == text[chunks[0].char_end - 20 : chunks[0].char_end]
        )

    def test_the_whole_document_is_covered(self) -> None:
        text = "x" * 250
        chunks = FixedSizeChunker(size=100, overlap=20).chunk(_document("d", text))
        assert chunks[-1].char_end == len(text)

    def test_an_empty_document_yields_nothing(self) -> None:
        assert FixedSizeChunker().chunk(_document("d", "   ")) == []

    def test_overlap_must_be_smaller_than_size(self) -> None:
        """Otherwise the window never advances and chunking never terminates."""
        with pytest.raises(ValueError, match="must be smaller"):
            FixedSizeChunker(size=100, overlap=100)

    def test_c0_chunks_carry_no_section_or_page(self) -> None:
        """Not an omission. A fixed window spans arbitrary parts of a document,
        so there is no section or page it honestly belongs to — which is what
        structure-aware chunking fixes in C1."""
        chunk = FixedSizeChunker(size=64, overlap=8).chunk(_document("d", "y" * 200))[0]
        assert chunk.section_path is None
        assert chunk.page_number is None

    def test_is_demo_propagates_to_every_chunk(self) -> None:
        chunks = FixedSizeChunker(size=64, overlap=8).chunk(
            _document("d", "z" * 400, demo=True)
        )
        assert chunks and all(chunk.is_demo for chunk in chunks)


class TestContextAssembly:
    def test_markers_follow_rank_order(self) -> None:
        context = assemble_context([_hit("a", "first"), _hit("b", "second")])
        assert "[S1]" in context.text and "[S2]" in context.text
        assert context.text.index("[S1]") < context.text.index("[S2]")
        assert [source.chunk_id for source in context.sources] == ["a", "b"]

    def test_the_budget_drops_from_the_tail_and_counts_it(self) -> None:
        hits = [_hit(str(i), "x" * 400) for i in range(10)]
        context = assemble_context(hits, max_chars=900)
        assert context.included < len(hits)
        assert context.dropped_for_budget == len(hits) - context.included

    def test_at_least_one_chunk_survives_an_impossible_budget(self) -> None:
        """Answering from a truncated chunk beats answering from nothing."""
        context = assemble_context([_hit("a", "y" * 5000)], max_chars=10)
        assert context.included == 1

    def test_a_demo_source_is_flagged_and_badged(self) -> None:
        context = assemble_context(
            [_hit("a", "real"), _hit("b", "synthetic", demo=True)]
        )
        assert context.contains_demo
        assert "[DEMO DATA]" in context.text

    def test_a_page_number_reaches_the_citation_label(self) -> None:
        context = assemble_context([_hit("a", "text", page=37)])
        assert "page 37" in context.text

    def test_no_hits_is_empty_not_an_error(self) -> None:
        assert assemble_context([]).is_empty


class TestPromptsDifferOnlyByConfiguration:
    def test_c0_gets_the_plain_system_prompt(self) -> None:
        system, _ = build_prompt(
            "q", assemble_context([_hit("a", "t")]), enforce_citations=False
        )
        assert system == BASE_SYSTEM

    def test_grounding_adds_citation_and_refusal_rules(self) -> None:
        system, _ = build_prompt(
            "q", assemble_context([_hit("a", "t")]), enforce_citations=True
        )
        assert system == GROUNDED_SYSTEM
        assert "citation marker" in system
        assert "Do not guess" in system

    def test_the_context_block_is_identical_either_way(self) -> None:
        """The only difference between C0 and C1+ prompts is the instructions.
        If the context format differed too, a measured difference could not be
        attributed to the retrieval change."""
        context = assemble_context([_hit("a", "shared content")])
        _, plain = build_prompt("q", context, enforce_citations=False)
        _, grounded = build_prompt("q", context, enforce_citations=True)
        assert context.text in plain
        assert context.text in grounded

    def test_no_context_instructs_against_answering_from_memory(self) -> None:
        _, body = build_prompt("q", assemble_context([]))
        assert "no information" in body.lower() or "general knowledge" in body.lower()


class TestDenseRetrieval:
    @pytest.fixture
    def indexed(self) -> tuple[InMemoryIndex, DeterministicEmbedder]:
        embedder, index = DeterministicEmbedder(), InMemoryIndex()
        chunker = FixedSizeChunker(size=200, overlap=20)
        documents = [
            _document(
                "intake",
                "Computer Engineering has a sanctioned intake of 180 students. " * 3,
            ),
            _document(
                "library",
                "The library subscribes to IEEE Xplore and Springer journals. " * 3,
            ),
            _document(
                "grievance",
                "A grievance is acknowledged within two working days. " * 3,
                demo=True,
            ),
        ]
        chunks = [chunk for document in documents for chunk in chunker.chunk(document)]
        index.add(chunks, embedder.embed_documents([chunk.content for chunk in chunks]))
        return index, embedder

    def test_the_relevant_document_ranks_first(self, indexed) -> None:
        index, embedder = indexed
        result = DenseRetriever(index, embedder).retrieve("sanctioned intake", top_k=3)
        assert result.hits[0].metadata["document_title"] == "Intake"

    def test_c0_populates_only_the_dense_stage(self, indexed) -> None:
        """A C0 row in retrieval_logs is distinguishable from a C2 row by the
        sparse and fused lists being empty."""
        index, embedder = indexed
        result = DenseRetriever(index, embedder).retrieve("intake", top_k=3)
        assert result.dense_hits == result.hits
        assert result.sparse_hits == []
        assert result.fused_hits == []
        assert result.reranked_hits == []

    def test_demo_sources_can_be_excluded(self, indexed) -> None:
        index, embedder = indexed
        retriever = DenseRetriever(index, embedder, include_demo_sources=False)
        result = retriever.retrieve("grievance acknowledged", top_k=5)
        assert all(not hit.is_demo for hit in result.hits)
        assert result.filters_applied == {"is_demo": False}

    def test_stage_latencies_are_recorded(self, indexed) -> None:
        index, embedder = indexed
        result = DenseRetriever(index, embedder).retrieve("intake", top_k=2)
        assert set(result.stage_latencies) == {"embed_query", "dense_search"}

    def test_the_log_shape_matches_the_retrieval_logs_columns(self, indexed) -> None:
        index, embedder = indexed
        log = DenseRetriever(index, embedder).retrieve("intake", top_k=2).to_log()
        for column in (
            "original_query",
            "rewritten_queries",
            "dense_hits",
            "sparse_hits",
            "fused_hits",
            "reranked_hits",
            "filters_applied",
            "stage_latencies",
            "iteration_count",
        ):
            assert column in log


class TestC0EndToEnd:
    @pytest.fixture
    def pipeline(self) -> tuple[Pipeline, _FakeGenerator]:
        generator = _FakeGenerator()
        pipeline = Pipeline(
            C0_BASELINE, DeterministicEmbedder(), InMemoryIndex(), generator
        )
        pipeline.index_documents(
            [
                _document(
                    "intake", "Computer Engineering intake is 180 students. " * 4
                ),
                _document(
                    "naac", "The institute holds NAAC A plus accreditation. " * 4
                ),
                _document(
                    "sop",
                    "A grievance is acknowledged in two working days. " * 4,
                    demo=True,
                ),
            ]
        )
        return pipeline, generator

    def test_indexing_reports_what_it_did(self) -> None:
        pipeline = Pipeline(
            C0_BASELINE, DeterministicEmbedder(), InMemoryIndex(), _FakeGenerator()
        )
        report = pipeline.index_documents([_document("a", "content " * 100)])
        assert report.documents == 1
        assert report.chunks > 0
        assert report.indexed == report.chunks

    def test_an_empty_document_is_counted_not_crashed_on(self) -> None:
        pipeline = Pipeline(
            C0_BASELINE, DeterministicEmbedder(), InMemoryIndex(), _FakeGenerator()
        )
        report = pipeline.index_documents([_document("empty", "   ")])
        assert report.skipped_empty == 1
        assert report.indexed == 0

    def test_asking_produces_an_answer_with_sources(self, pipeline) -> None:
        pipe, _ = pipeline
        answer = pipe.ask("What is the intake?")
        assert answer.answer
        assert answer.sources
        assert answer.config_name == "C0"

    def test_the_answer_records_the_configuration_that_produced_it(
        self, pipeline
    ) -> None:
        pipe, _ = pipeline
        answer = pipe.ask("intake")
        assert answer.metadata["innovations"] == []
        assert answer.to_log()["config"] == "C0"

    def test_c0_does_not_ask_for_citations(self, pipeline) -> None:
        pipe, generator = pipeline
        pipe.ask("intake")
        assert generator.system == BASE_SYSTEM

    def test_demo_use_is_surfaced_on_the_answer(self, pipeline) -> None:
        pipe, _ = pipeline
        answer = pipe.ask("How long to acknowledge a grievance?")
        assert answer.used_demo_sources
        assert "[DEMO DATA]" in answer.format()

    def test_the_formatted_answer_lists_its_sources(self, pipeline) -> None:
        pipe, _ = pipeline
        rendered = pipe.ask("intake").format()
        assert "Sources:" in rendered
        assert "[S1]" in rendered
        assert "C0" in rendered
