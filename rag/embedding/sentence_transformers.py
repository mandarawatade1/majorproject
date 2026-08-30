"""Sentence-BERT embeddings via sentence-transformers.

The default backend, and the one the report commits to: BAAI/bge-small-en-v1.5,
384 dimensions, from the Sentence-BERT family named in Report section 3.2.1.

The query prefix matters. bge models are trained asymmetrically — queries carry
an instruction prefix that stored passages must not. Omitting it is a silent
quality loss, not an error, so it is applied here rather than left to callers.
"""

from __future__ import annotations

from typing import Any

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_DIMENSION = 384

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
"""The prefix bge-small expects on queries only. Applying it to documents, or
omitting it from queries, degrades retrieval measurably."""


class SentenceTransformerEmbedder:
    """Local Sentence-BERT embeddings. Downloads the model on first use."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        dimension: int = DEFAULT_DIMENSION,
        batch_size: int = 32,
        cache_folder: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.dimension = dimension
        self.batch_size = batch_size
        self._cache_folder = cache_folder
        self._model: Any | None = None

    # ------------------------------------------------------------------

    @property
    def model(self) -> Any:
        """Loaded lazily so importing this module costs nothing.

        Constructing an embedder must stay cheap: the CLI builds one to read
        its `model_name` for a log line long before anything is embedded, and
        loading a transformer for that would be absurd.
        """
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - dependency guard
                raise RuntimeError(
                    "sentence-transformers is not installed. Either install it "
                    "(pip install sentence-transformers) or switch to the Ollama "
                    "backend, which needs no torch: set EMBEDDING_BACKEND=ollama."
                ) from exc

            self._model = SentenceTransformer(
                self.model_name, cache_folder=self._cache_folder
            )

            actual = int(self._model.get_sentence_embedding_dimension())
            if actual != self.dimension:
                # A dimension mismatch corrupts an index silently: vectors go
                # in, similarity is meaningless, nothing errors.
                raise ValueError(
                    f"{self.model_name} produces {actual}-dimensional vectors but the "
                    f"configuration expects {self.dimension}. Fix EMBEDDING_DIMENSION, "
                    f"and rebuild any index created with the other value."
                )
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        vector = self.model.encode(
            QUERY_PREFIX + text,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return list(vector.tolist())
