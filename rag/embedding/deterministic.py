"""A deterministic, dependency-free embedder for tests.

Not a semantic model — it hashes token n-grams into a fixed-width vector. What
it does provide is everything the pipeline's plumbing needs to be tested:
stable vectors, correct dimensionality, unit norm, and enough lexical signal
that a query about "intake" ranks a chunk containing "intake" above one that
does not.

This is what lets Phase 3's indexing, retrieval and context assembly be tested
without downloading a model or installing torch. It must never be used to
produce a number that appears in the report.
"""

from __future__ import annotations

import hashlib
import math
import re

_TOKEN = re.compile(r"[a-z0-9]+")


class DeterministicEmbedder:
    """Hashing embedder. Same text in, same vector out, on any machine."""

    def __init__(self, dimension: int = 384) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self.model_name = f"deterministic-hash-{dimension}"
        self.dimension = dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    # ------------------------------------------------------------------

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = _TOKEN.findall(text.lower())

        for token in tokens:
            vector[self._bucket(token)] += 1.0

        # Bigrams give a little word-order signal, so that "computer
        # engineering" is not identical to "engineering computer".
        for first, second in zip(tokens, tokens[1:], strict=False):
            vector[self._bucket(f"{first}_{second}")] += 0.5

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]

    def _bucket(self, token: str) -> int:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big") % self.dimension
