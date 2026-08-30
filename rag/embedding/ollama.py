"""Embeddings via the Ollama server.

An escape hatch, not the default. sentence-transformers pulls in torch, which
is roughly 2.5 GB in the image and a slow build. Ollama is already running for
generation, so this backend produces embeddings with no extra dependency at all.

The trade-off is honesty about the report: Report section 3.2.1 commits to
Sentence-BERT, so a run using this backend is a deviation and must be labelled
as one. `model_name` is recorded on every chunk and in every retrieval log
precisely so a result can never be misattributed to the wrong embedder.
"""

from __future__ import annotations

import httpx

DEFAULT_MODEL = "nomic-embed-text"
DEFAULT_DIMENSION = 768


class OllamaEmbedder:
    """Embeddings from a local Ollama server."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model_name: str = DEFAULT_MODEL,
        dimension: int = DEFAULT_DIMENSION,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.dimension = dimension
        self.timeout = timeout

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    # ------------------------------------------------------------------

    def _embed(self, text: str) -> list[float]:
        try:
            response = httpx.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model_name, "prompt": text},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Ollama embedding request failed against {self.base_url}: {exc}. "
                f"Is the model pulled? `ollama pull {self.model_name}`"
            ) from exc

        vector = response.json().get("embedding")
        if not vector:
            raise RuntimeError(
                f"Ollama returned no embedding for model {self.model_name}"
            )

        if len(vector) != self.dimension:
            raise ValueError(
                f"{self.model_name} returned {len(vector)} dimensions, expected "
                f"{self.dimension}. Fix EMBEDDING_DIMENSION and rebuild the index."
            )
        return [float(value) for value in vector]
