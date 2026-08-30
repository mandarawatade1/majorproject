"""An in-process vector index.

Exists so the whole pipeline — chunk, embed, index, retrieve, assemble context
— can be tested with no Chroma server, no network and no model download. Brute
force cosine over a list, which is fine for a few thousand chunks and hopeless
beyond that, hence Chroma for the real corpus.
"""

from __future__ import annotations

from typing import Any

from rag.chunking.base import Chunk
from rag.indexing.base import IndexedHit


class InMemoryIndex:
    name = "memory"

    def __init__(self) -> None:
        self._vectors: dict[str, list[float]] = {}
        self._content: dict[str, str] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> int:
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        for chunk, vector in zip(chunks, vectors, strict=True):
            self._vectors[chunk.chunk_id] = vector
            self._content[chunk.chunk_id] = chunk.content
            self._metadata[chunk.chunk_id] = chunk.to_metadata()
        return len(chunks)

    def search(
        self,
        vector: list[float],
        top_k: int,
        where: dict[str, Any] | None = None,
    ) -> list[IndexedHit]:
        hits: list[IndexedHit] = []
        for chunk_id, stored in self._vectors.items():
            metadata = self._metadata[chunk_id]
            if where and any(
                metadata.get(key) != value for key, value in where.items()
            ):
                continue
            hits.append(
                IndexedHit(
                    chunk_id=chunk_id,
                    content=self._content[chunk_id],
                    score=_cosine(vector, stored),
                    metadata=metadata,
                )
            )
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:top_k]

    def count(self) -> int:
        return len(self._vectors)

    def reset(self) -> None:
        self._vectors.clear()
        self._content.clear()
        self._metadata.clear()


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"dimension mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    # Both embedders normalise, so the dot product is already the cosine. Not
    # re-normalising here keeps a mismatch visible rather than papering over it.
    return float(dot)
