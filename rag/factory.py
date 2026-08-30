"""Build pipeline components from environment configuration.

Kept separate from `pipeline.py` so the orchestrator stays a pure composition
of protocols and can be constructed with test doubles. This module is the only
place that reads the environment or imports a heavy optional dependency.
"""

from __future__ import annotations

import os

from rag.config import PipelineConfig
from rag.embedding.base import Embedder
from rag.generation.base import Generator
from rag.indexing.base import VectorIndex
from rag.indexing.bm25 import BM25Index
from rag.pipeline import Pipeline


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def build_embedder(backend: str | None = None) -> Embedder:
    """Construct the configured embedding backend.

    Default is sentence-transformers, which is what Report section 3.2.1
    commits to. `EMBEDDING_BACKEND=ollama` avoids installing torch; `fake` is
    for tests and must never produce a reported number.
    """
    backend = (backend or _env("EMBEDDING_BACKEND", "sentence-transformers")).lower()

    if backend in {"fake", "deterministic"}:
        from rag.embedding.deterministic import DeterministicEmbedder

        return DeterministicEmbedder(int(_env("EMBEDDING_DIMENSION", "384")))

    if backend == "ollama":
        from rag.embedding.ollama import OllamaEmbedder

        return OllamaEmbedder(
            base_url=_env("OLLAMA_BASE_URL", "http://localhost:11434"),
            model_name=_env("EMBEDDING_MODEL", "nomic-embed-text"),
            dimension=int(_env("EMBEDDING_DIMENSION", "768")),
        )

    from rag.embedding.sentence_transformers import SentenceTransformerEmbedder

    return SentenceTransformerEmbedder(
        model_name=_env("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
        dimension=int(_env("EMBEDDING_DIMENSION", "384")),
        cache_folder=os.environ.get("HF_HOME"),
    )


def build_index(
    embedding_model: str, chunking: str = "", backend: str | None = None
) -> VectorIndex:
    """Construct the vector index.

    `embedding_model` and `chunking` are stored on the collection so a later
    run that differs in either is refused rather than silently searching an
    index it cannot compare against. Both matter for the same reason: a
    mismatch does not error on its own, it just returns confident results
    computed over the wrong thing.
    """
    backend = (backend or _env("INDEX_BACKEND", "chroma")).lower()

    if backend == "memory":
        from rag.indexing.memory import InMemoryIndex

        return InMemoryIndex()

    from rag.indexing.chroma import ChromaIndex

    return ChromaIndex(
        host=_env("CHROMA_HOST", "localhost"),
        port=int(_env("CHROMA_PORT", "8000")),
        collection=_env("CHROMA_COLLECTION", "pce_chunks"),
        embedding_model=embedding_model,
        chunking=chunking,
    )


def build_sparse_index(path: str | None = None) -> BM25Index:
    """Construct the BM25 sparse index.

    Stored on disk, separately from the dense index, so it can be rebuilt or
    inspected without a running Chroma server. One path per collection, same
    idea as CHROMA_COLLECTION scoping the dense index -- keeps a C0/C1 run
    (which never touches this file) from having any way to disturb a C2 run.
    """
    return BM25Index(path=path or _env("BM25_INDEX_PATH", "./data/bm25/index.pkl"))


def build_generator() -> Generator:
    from rag.generation.ollama import OllamaGenerator

    return OllamaGenerator(
        base_url=_env("OLLAMA_BASE_URL", "http://localhost:11434"),
        model_name=_env("OLLAMA_GENERATOR_MODEL", "qwen2.5:7b-instruct-q4_K_M"),
        temperature=float(_env("LLM_TEMPERATURE", "0.1")),
        max_tokens=int(_env("LLM_MAX_TOKENS", "1024")),
        timeout=float(_env("LLM_TIMEOUT_SECONDS", "180")),
    )


def build_pipeline(config: PipelineConfig) -> Pipeline:
    # C5's verifier needs no factory of its own: it runs on the generator the
    # pipeline already holds, deliberately, so the system verifies itself with
    # its own model rather than borrowing the evaluation judge.
    embedder = build_embedder()
    sparse_index = build_sparse_index() if config.uses_sparse else None
    return Pipeline(
        config=config,
        embedder=embedder,
        index=build_index(embedder.model_name, config.chunking.value),
        generator=build_generator(),
        sparse_index=sparse_index,
    )


__all__ = [
    "build_embedder",
    "build_generator",
    "build_index",
    "build_pipeline",
    "build_sparse_index",
]
