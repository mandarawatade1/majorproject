"""BM25 sparse index — the keyword-matching half of C2's hybrid retrieval.

Dense search finds vectors that mean the same thing; it also lets through
vectors that read as similar without ever using the actual words in the
query. BM25 catches literal-term matches -- a query for "NBA accredited"
should surface a chunk containing those exact words even if it is not the
top dense neighbour. Neither arm is a substitute for the other; RRF fusion in
`rag/retrieval/hybrid.py` is what combines them.

Stored on disk as a single pickle file, not inside Chroma, so its lifecycle
does not depend on a running vector database. It carries no truth PostgreSQL
does not already have -- rebuildable at any time from the same chunks the
dense index holds, same as Chroma's own collection.

Requires `rank_bm25` (pure Python, no torch): add to backend/requirements.txt.
"""

from __future__ import annotations

import pickle
import re
from pathlib import Path
from typing import Any

from rag.chunking.base import Chunk
from rag.indexing.base import IndexedHit

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


# Applied to the QUERY only, never to documents. Filtering documents would
# change the collection statistics BM25 scores against -- document frequency
# and average length -- and so would require rebuilding the index. Filtering
# only the query leaves those statistics untouched and still removes the
# terms that were doing the damage.
#
# Measured on the question "What subjects are in Semester I of Mechanical
# Engineering?", which BM25 ranked 11th behind a page titled "The best college
# experience!": the query carried `what`, `are`, `in` and `of`, present in up
# to 2,759 of 4,114 chunks, so any page repeating "mechanical engineering"
# outscored the one table that answered the question. Dropping them moves the
# correct passage from 11th to 2nd.
#
# `i` is deliberately ABSENT from this list even though it is a pronoun. It is
# also the roman numeral that separates "Semester I" from "Semester IV", "VI"
# and "VIII" -- fourteen near-identical tables in one syllabus. Removing it
# was tried and made the same question worse, 11th to 35th, because it deleted
# the only evidence distinguishing the semesters. Single letters carry meaning
# in a course catalogue.
_QUERY_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
        "for", "from", "how", "is", "in", "it", "of", "on", "or", "that",
        "the", "to", "was", "what", "when", "where", "which", "who", "why",
        "with",
    }
)


def _tokenize_query(text: str) -> list[str]:
    """Tokenise a question, dropping terms that carry no discriminating power.

    Falls back to the unfiltered tokens if filtering would empty the query --
    a question made entirely of stopwords should still retrieve something.
    """
    tokens = _tokenize(text)
    kept = [token for token in tokens if token not in _QUERY_STOPWORDS]
    return kept or tokens


class BM25Index:
    """Sparse keyword index, persisted to a pickle file on disk."""

    name = "bm25"

    def __init__(self, path: str = "./data/bm25/index.pkl") -> None:
        self.path = Path(path)
        self._chunk_ids: list[str] = []
        self._contents: list[str] = []
        self._metadatas: list[dict[str, Any]] = []
        self._tokenized: list[list[str]] = []
        self._bm25: Any | None = None
        self._id_to_pos: dict[str, int] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        if self.path.exists():
            with open(self.path, "rb") as f:
                state = pickle.load(f)
            self._chunk_ids = state["chunk_ids"]
            self._contents = state["contents"]
            self._metadatas = state["metadatas"]
            self._tokenized = state["tokenized"]
            self._id_to_pos = {cid: i for i, cid in enumerate(self._chunk_ids)}
            self._rebuild_model()
        self._loaded = True

    def _rebuild_model(self) -> None:
        from rank_bm25 import BM25Okapi

        self._bm25 = BM25Okapi(self._tokenized) if self._tokenized else None

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "wb") as f:
            pickle.dump(
                {
                    "chunk_ids": self._chunk_ids,
                    "contents": self._contents,
                    "metadatas": self._metadatas,
                    "tokenized": self._tokenized,
                },
                f,
            )

    def add(self, chunks: list[Chunk]) -> int:
        """Upsert chunks by chunk_id. No vectors needed -- BM25 works on text."""
        self._ensure_loaded()
        added = 0
        for chunk in chunks:
            tokens = _tokenize(chunk.embed_text)
            metadata = chunk.to_metadata()
            if chunk.chunk_id in self._id_to_pos:
                pos = self._id_to_pos[chunk.chunk_id]
                self._contents[pos] = chunk.content
                self._metadatas[pos] = metadata
                self._tokenized[pos] = tokens
            else:
                self._id_to_pos[chunk.chunk_id] = len(self._chunk_ids)
                self._chunk_ids.append(chunk.chunk_id)
                self._contents.append(chunk.content)
                self._metadatas.append(metadata)
                self._tokenized.append(tokens)
                added += 1
        self._rebuild_model()
        self._persist()
        return added

    def search(
        self,
        query: str,
        top_k: int,
        where: dict[str, Any] | None = None,
    ) -> list[IndexedHit]:
        self._ensure_loaded()
        if self._bm25 is None or not self._chunk_ids:
            return []

        query_tokens = _tokenize_query(query)
        scores = self._bm25.get_scores(query_tokens)

        candidates = list(range(len(self._chunk_ids)))
        if where:
            candidates = [
                i
                for i in candidates
                if all(self._metadatas[i].get(k) == v for k, v in where.items())
            ]

        ranked = sorted(candidates, key=lambda i: scores[i], reverse=True)[:top_k]

        return [
            IndexedHit(
                chunk_id=self._chunk_ids[i],
                content=self._contents[i],
                score=float(scores[i]),
                metadata=dict(self._metadatas[i]),
            )
            for i in ranked
            if scores[i] > 0
        ]

    def count(self) -> int:
        self._ensure_loaded()
        return len(self._chunk_ids)

    def reset(self) -> None:
        self._chunk_ids = []
        self._contents = []
        self._metadatas = []
        self._tokenized = []
        self._bm25 = None
        self._id_to_pos = {}
        self._loaded = True
        if self.path.exists():
            self.path.unlink()
