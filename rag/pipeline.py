"""The orchestrator: assembles a pipeline from a PipelineConfig and runs it.

Every configuration, C0 through C5, runs through this one class. The stages it
builds differ; the sequence, the context assembly, the prompt format and the
logging do not. That is what makes the Chapter 4 numbers attributable — a
difference between two runs is a difference in the stages the config selected,
because nothing else varied.

A configuration whose stages are not built yet is refused rather than silently
approximated. Running "C3" today and getting C0's behaviour would put a wrong
number in the report under a right-looking label, which is worse than an error.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from rag.agentic.graph import AgenticRetriever
from rag.chunking.base import Chunk, Chunker
from rag.chunking.fixed import FixedSizeChunker
from rag.chunking.semantic import StructureAwareChunker
from rag.config import (
    ChunkingStrategy,
    PipelineConfig,
    RetrievalStrategy,
    implemented_configs,
)
from rag.embedding.base import Embedder
from rag.generation.base import GenerationResult, Generator
from rag.generation.prompts import (
    REFUSAL_TEXT,
    AssembledContext,
    assemble_context,
    build_prompt,
    format_sources,
)
from rag.indexing.base import VectorIndex
from rag.indexing.bm25 import BM25Index
from rag.ingestion.models import ParsedDocument
from rag.reranking.cross_encoder import CrossEncoderReranker
from rag.retrieval.base import RetrievalResult, stage_timer
from rag.retrieval.dense import DenseRetriever
from rag.retrieval.hybrid import HybridRetriever
from rag.verification.base import VerificationResult, Verifier
from rag.verification.claim_check import ClaimVerifier


@dataclass(slots=True)
class Answer:
    """One answered question, with everything needed to explain or score it."""

    question: str
    answer: str
    config_name: str
    model_name: str

    context: AssembledContext | None = None
    retrieval: RetrievalResult | None = None

    verification: VerificationResult | None = None
    """Populated only by C5. None for every earlier configuration, so a C5 row
    is distinguishable from a C4 row by its presence -- the same convention
    `RetrievalResult.stop_reason` follows for C4."""

    latency_ms: float = 0.0
    generation_ms: float = 0.0
    retrieval_ms: float = 0.0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def sources(self) -> list[Any]:
        return self.context.sources if self.context else []

    @property
    def used_demo_sources(self) -> bool:
        return bool(self.context and self.context.contains_demo)

    def format(self) -> str:
        parts = (
            [self.answer, "", format_sources(self.context)]
            if self.context
            else [self.answer]
        )
        note = self._verification_note()
        if note:
            parts += ["", note]

        parts.append("")
        parts.append(
            f"[{self.config_name} | {self.model_name} | "
            f"retrieval {self.retrieval_ms:.0f}ms, generation {self.generation_ms:.0f}ms]"
        )
        return "\n".join(parts)

    def _verification_note(self) -> str:
        """What C5 tells the reader, if anything.

        A refusal says what was withheld and shows the withheld text. Silently
        replacing an answer would make C5 unauditable: a reader could not tell
        whether it suppressed a hallucination or destroyed a good answer, and
        that is exactly the question a refusal invites.
        """
        v = self.verification
        if v is None:
            return ""

        if v.refused:
            return (
                "  VERIFICATION: no sentence of the generated answer was supported "
                "by its cited sources, so the answer was withheld.\n"
                f"  Withheld text: {v.original_answer.strip()}"
            )
        if v.unsupported:
            listed = ", ".join(str(n) for n in v.unsupported)
            rate = v.support_rate
            return (
                f"  VERIFICATION: sentence(s) {listed} of {v.checked} were not "
                f"supported by the cited sources"
                + (f" ({rate:.0%} supported)." if rate is not None else ".")
            )
        if v.verdict.value == "unparseable":
            return (
                "  VERIFICATION: the check could not be read, so the answer is "
                "shown unchanged and unverified."
            )
        return ""

    def to_log(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "config": self.config_name,
            "model": self.model_name,
            "latency_ms": round(self.latency_ms, 1),
            "retrieval_ms": round(self.retrieval_ms, 1),
            "generation_ms": round(self.generation_ms, 1),
            "sources": [h.chunk_id for h in self.sources],
            "used_demo_sources": self.used_demo_sources,
            "retrieval": self.retrieval.to_log() if self.retrieval else None,
            "verification": (self.verification.to_log() if self.verification else None),
        }


@dataclass(slots=True)
class Prepared:
    """The state of an answer just before the model is called.

    Exists so `ask()` and the API's streaming path share one retrieval and one
    prompt. A portal answer that differed from the measured one would make
    Chapter 4 describe a system the user never used.
    """

    question: str
    retrieval: RetrievalResult
    context: AssembledContext
    system: str
    prompt: str
    retrieval_ms: float


@dataclass(slots=True)
class IndexReport:
    documents: int = 0
    chunks: int = 0
    indexed: int = 0
    skipped_empty: int = 0
    elapsed_s: float = 0.0

    def summary(self) -> str:
        rate = self.chunks / self.elapsed_s if self.elapsed_s else 0.0
        return (
            f"indexed {self.indexed} chunks from {self.documents} documents "
            f"in {self.elapsed_s:.1f}s ({rate:.0f} chunks/s)"
            + (
                f", {self.skipped_empty} document(s) had no content"
                if self.skipped_empty
                else ""
            )
        )


class Pipeline:
    """Chunk, embed, index, retrieve, rerank, generate — driven by a PipelineConfig."""

    def __init__(
        self,
        config: PipelineConfig,
        embedder: Embedder,
        index: VectorIndex,
        generator: Generator,
        sparse_index: BM25Index | None = None,
    ) -> None:
        _require_implemented(config)
        self.config = config
        self.embedder = embedder
        self.index = index
        self.generator = generator
        self.sparse_index = sparse_index

        self.chunker: Chunker = _build_chunker(config)
        self.retriever = _build_retriever(
            config, index, embedder, sparse_index, generator
        )
        self.reranker: CrossEncoderReranker | None = _build_reranker(config)
        self.verifier: Verifier | None = _build_verifier(config, generator)

    # --- Indexing -----------------------------------------------------

    def index_documents(
        self, documents: list[ParsedDocument], batch_size: int = 64
    ) -> IndexReport:
        """Chunk, embed and index. Embedding is batched because it dominates."""
        report = IndexReport(documents=len(documents))
        started = time.perf_counter()

        pending: list[Chunk] = []
        for document in documents:
            chunks = self.chunker.chunk(document)
            if not chunks:
                report.skipped_empty += 1
                continue
            report.chunks += len(chunks)
            pending.extend(chunks)

            while len(pending) >= batch_size:
                report.indexed += self._flush(pending[:batch_size])
                del pending[:batch_size]

        if pending:
            report.indexed += self._flush(pending)

        report.elapsed_s = time.perf_counter() - started
        return report

    def _flush(self, chunks: list[Chunk]) -> int:
        vectors = self.embedder.embed_documents([chunk.content for chunk in chunks])
        indexed = self.index.add(chunks, vectors)
        if self.sparse_index is not None:
            self.sparse_index.add(chunks)
        return indexed

    # --- Answering ----------------------------------------------------

    def prepare(self, question: str) -> Prepared:
        """Everything up to the point of generation.

        Split out of `ask()` so the streaming path in the API can reuse it
        rather than reimplementing retrieval. That reuse is not a convenience:
        if the portal assembled its context or built its prompt even slightly
        differently, the answers a user sees would not be the answers Chapter 4
        measured, and no amount of care elsewhere would make them comparable
        again. One implementation, two callers.
        """
        retrieval = self.retriever.retrieve(question, top_k=self.config.dense_top_k)

        context_hits = retrieval.hits
        if self.reranker is not None:
            with stage_timer(retrieval, "rerank"):
                reranked = self.reranker.rerank(
                    question, retrieval.hits, top_n=self.config.rerank_top_n
                )
            retrieval.reranked_hits = reranked
            context_hits = reranked

        context = assemble_context(
            context_hits, max_chars=self.config.max_context_chars
        )
        system, prompt = build_prompt(
            question, context, enforce_citations=self.config.enforce_citations
        )
        return Prepared(
            question=question,
            retrieval=retrieval,
            context=context,
            system=system,
            prompt=prompt,
            retrieval_ms=sum(retrieval.stage_latencies.values()),
        )

    def finish(
        self, prepared: Prepared, generated: GenerationResult, started: float
    ) -> Answer:
        """Verification and assembly, shared by the blocking and streaming paths."""
        answer_text = generated.answer
        verification = None
        if self.verifier is not None:
            verification = self.verifier.verify(
                prepared.question, answer_text, prepared.context
            )
            if verification.refused:
                answer_text = REFUSAL_TEXT

        return Answer(
            question=prepared.question,
            answer=answer_text,
            config_name=self.config.name,
            model_name=generated.model_name,
            context=prepared.context,
            retrieval=prepared.retrieval,
            verification=verification,
            latency_ms=(time.perf_counter() - started) * 1000,
            generation_ms=generated.latency_ms,
            retrieval_ms=prepared.retrieval_ms,
            prompt_tokens=generated.prompt_tokens,
            completion_tokens=generated.completion_tokens,
            metadata={
                "innovations": self.config.innovations_enabled,
                "context_chunks": prepared.context.included,
                "context_dropped": prepared.context.dropped_for_budget,
            },
        )

    def ask(self, question: str) -> Answer:
        """Answer one question. The path every Chapter 4 number came from."""
        started = time.perf_counter()
        prepared = self.prepare(question)

        # C5's check happens inside `finish`. Generation here is byte-for-byte
        # C4's -- same context, same prompt, same call -- so a C4-to-C5
        # difference is the verification and nothing else.
        generated = self.generator.generate(prepared.prompt, system=prepared.system)
        return self.finish(prepared, generated, started)


# ---------------------------------------------------------------------------


def _require_implemented(config: PipelineConfig) -> None:
    available = implemented_configs()
    if config.name in available:
        return
    missing = ", ".join(config.innovations_enabled) or "features"
    raise NotImplementedError(
        f"Configuration {config.name} requires {missing}, which are not built yet. "
        f"Implemented today: {', '.join(available)}. Running it would produce "
        f"{available[0]}'s behaviour under {config.name}'s name, which would put a "
        f"wrong number in the evaluation."
    )


def _build_chunker(config: PipelineConfig) -> Chunker:
    if config.chunking is ChunkingStrategy.FIXED:
        return FixedSizeChunker(
            size=config.chunk_size_chars, overlap=config.chunk_overlap_chars
        )
    if config.chunking is ChunkingStrategy.STRUCTURE_AWARE:
        return StructureAwareChunker(
            max_size=config.chunk_max_tokens * 4,
            overlap=config.chunk_overlap_chars,
        )
    raise NotImplementedError(
        f"chunking strategy '{config.chunking.value}' arrives in Phase 4"
    )


def _build_verifier(config: PipelineConfig, generator: Generator) -> Verifier | None:
    """C5's verifier, or nothing.

    Deliberately given the *generator's* model rather than the evaluation
    judge. The verifier is part of the system under test; the judge scores that
    system from outside. Wiring the judge in here would put the examiner inside
    the thing being examined, and no Chapter 4 number computed that way would
    mean what it appears to mean.
    """
    if not config.verify_answer:
        return None
    return ClaimVerifier(generator=generator)


def _build_retriever(
    config: PipelineConfig,
    index: VectorIndex,
    embedder: Embedder,
    sparse_index: BM25Index | None,
    generator: Generator,
) -> DenseRetriever | HybridRetriever | AgenticRetriever:
    """Build the retriever the configuration asks for.

    C4 does not replace the retriever — it WRAPS it. The agent runs whatever
    retrieval strategy the config already selected (hybrid, for C4), several
    times, and returns the accumulated pool. Reranking, context assembly,
    prompt and generation downstream are then byte-for-byte the C3 path, which
    is what keeps the ablation single-variable.
    """
    base = _build_base_retriever(config, index, embedder, sparse_index)

    if config.agentic:
        return AgenticRetriever(
            retriever=base,
            generator=generator,
            max_iterations=config.agent_max_iterations,
        )
    return base


def _build_base_retriever(
    config: PipelineConfig,
    index: VectorIndex,
    embedder: Embedder,
    sparse_index: BM25Index | None,
) -> DenseRetriever | HybridRetriever:
    if config.retrieval is RetrievalStrategy.DENSE:
        return DenseRetriever(
            index=index,
            embedder=embedder,
            include_demo_sources=config.include_demo_sources,
        )
    if config.retrieval is RetrievalStrategy.HYBRID:
        if sparse_index is None:
            raise RuntimeError(
                "hybrid retrieval requires a sparse_index, but none was built. "
                "This is a factory wiring bug, not a missing feature."
            )
        return HybridRetriever(
            index=index,
            sparse_index=sparse_index,
            embedder=embedder,
            dense_top_k=config.dense_top_k,
            sparse_top_k=config.sparse_top_k,
            rrf_k=config.rrf_k,
            include_demo_sources=config.include_demo_sources,
        )
    raise NotImplementedError(
        f"retrieval strategy '{config.retrieval.value}' arrives in Phase 4"
    )


def _build_reranker(config: PipelineConfig) -> CrossEncoderReranker | None:
    if not config.rerank:
        return None
    return CrossEncoderReranker()


__all__ = ["Answer", "IndexReport", "Pipeline"]
