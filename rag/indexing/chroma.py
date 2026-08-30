"""ChromaDB vector index.

PostgreSQL holds the truth; this holds an index. Chunk ids here are the same
UUIDs the `chunks` table uses, so the collection can be dropped and rebuilt
from the database at any time without losing anything.

The collection records which embedding model built it. Searching an index with
a different model than built it does not error — it returns confident,
meaningless results — so the mismatch is checked rather than trusted.
"""

from __future__ import annotations

import contextlib
from typing import Any

from rag.chunking.base import Chunk
from rag.indexing.base import IndexedHit

DEFAULT_COLLECTION = "pce_chunks"


class ChromaIndex:
    """Dense index backed by a Chroma server."""

    name = "chroma"

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8000,
        collection: str = DEFAULT_COLLECTION,
        embedding_model: str = "",
        chunking: str = "",
        batch_size: int = 256,
    ) -> None:
        self.host = host
        self.port = port
        self.collection_name = collection
        self.embedding_model = embedding_model
        self.chunking = chunking
        self.batch_size = batch_size
        self._client: Any | None = None
        self._collection: Any | None = None

    # ------------------------------------------------------------------

    @property
    def collection(self) -> Any:
        if self._collection is None:
            self._collection = self._open()
        return self._collection

    def _open(self) -> Any:
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "chromadb is not installed: pip install chromadb"
            ) from exc

        self._client = chromadb.HttpClient(host=self.host, port=self.port)

        collection = self._client.get_or_create_collection(
            name=self.collection_name,
            # Cosine, because both embedders emit unit vectors and the report
            # specifies cosine similarity.
            metadata={
                "hnsw:space": "cosine",
                "embedding_model": self.embedding_model,
                "chunking": self.chunking,
            },
        )

        stored = collection.metadata or {}
        self._check(
            "embedding model", stored.get("embedding_model"), self.embedding_model
        )
        # The same argument, for the same reason. C0 chunks every 512
        # characters; C1 onward chunks on section boundaries. Indexing both
        # into one collection without resetting leaves a mixture, and every
        # configuration then retrieves over some other configuration's chunks
        # — a contaminated Chapter 4 with nothing anywhere reporting a fault.
        # Note this cannot protect a collection built before the key existed:
        # an older collection has no `chunking` recorded, so the first rebuild
        # is what starts the protection.
        self._check("chunking strategy", stored.get("chunking"), self.chunking)
        return collection

    def _check(self, label: str, existing: Any, current: str) -> None:
        if existing and current and existing != current:
            raise RuntimeError(
                f"Collection '{self.collection_name}' was built with {label} "
                f"'{existing}' but this run uses '{current}'. Searching it would "
                f"return confident, meaningless results rather than failing. "
                f"Re-index with --reset, or set CHROMA_COLLECTION to a different "
                f"collection for this configuration."
            )

    # ------------------------------------------------------------------

    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> int:
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        if not chunks:
            return 0

        for start in range(0, len(chunks), self.batch_size):
            window = slice(start, start + self.batch_size)
            batch = chunks[window]
            self.collection.upsert(
                ids=[chunk.chunk_id for chunk in batch],
                embeddings=vectors[window],
                documents=[chunk.content for chunk in batch],
                metadatas=[chunk.to_metadata() for chunk in batch],
            )
        return len(chunks)

    def search(
        self,
        vector: list[float],
        top_k: int,
        where: dict[str, Any] | None = None,
    ) -> list[IndexedHit]:
        result = self.collection.query(
            query_embeddings=[vector],
            n_results=top_k,
            where=where or None,
            include=["documents", "metadatas", "distances"],
        )

        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        hits: list[IndexedHit] = []
        for chunk_id, content, metadata, distance in zip(
            ids, documents, metadatas, distances, strict=False
        ):
            hits.append(
                IndexedHit(
                    chunk_id=str(chunk_id),
                    content=content or "",
                    # Chroma returns cosine DISTANCE; similarity is 1 - d.
                    # Reporting distance as a score would invert every ranking
                    # in the logs while leaving the order correct, which is the
                    # kind of discrepancy nobody finds until Chapter 4.
                    score=1.0 - float(distance),
                    metadata=dict(metadata or {}),
                )
            )
        return hits

    def count(self) -> int:
        return int(self.collection.count())

    def reset(self) -> None:
        """Drop and recreate the collection."""
        if self._client is None:
            self._open()
        assert self._client is not None
        # An absent collection is not an error — reset means "end up empty".
        with contextlib.suppress(Exception):
            self._client.delete_collection(self.collection_name)
        self._collection = None
        self._open()
