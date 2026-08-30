"""The embedding protocol."""

from __future__ import annotations

from typing import Protocol


class Embedder(Protocol):
    """Turns text into vectors.

    `embed_documents` and `embed_query` are separate because some models use an
    asymmetric scheme — a query prefix that must not be applied to stored text.
    bge is one of them, so the distinction is load-bearing rather than
    cosmetic: embedding a query as if it were a document measurably degrades
    retrieval.
    """

    model_name: str
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...
