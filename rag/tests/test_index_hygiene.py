"""Guards against silently indexing the wrong thing.

Every failure this file covers has the same shape: nothing raises, the run
completes, the numbers look plausible, and they were computed over a corpus
that is not the one the configuration describes. That is the single worst
outcome available to this project, so the guards get their own file.

No Chroma server is needed. `ChromaIndex._open` is exercised against a fake
client, because what is being tested is the guard's logic, not Chroma's.
"""

from __future__ import annotations

import pytest

from rag.chunking.fixed import FixedSizeChunker
from rag.chunking.semantic import StructureAwareChunker
from rag.indexing.bm25 import BM25Index
from rag.indexing.chroma import ChromaIndex
from rag.ingestion.models import DocumentCategory, ParsedDocument, SourceType


def _document(text: str = "alpha beta gamma delta " * 40) -> ParsedDocument:
    return ParsedDocument(
        doc_id="d",
        title="Doc",
        source_type=SourceType.WEB_HTML,
        category=DocumentCategory.PROGRAMME,
        text=text,
        source_url="https://www.pce.ac.in/d",
    )


class _FakeCollection:
    def __init__(self, metadata: dict) -> None:
        self.metadata = metadata


class _FakeClient:
    """Mimics `get_or_create_collection`: an existing collection keeps its own
    metadata, and the caller's metadata is ignored — which is precisely why the
    guard has to compare rather than assume."""

    def __init__(self, existing: dict | None = None) -> None:
        self.existing = existing

    def get_or_create_collection(self, name: str, metadata: dict) -> _FakeCollection:
        return _FakeCollection(self.existing if self.existing is not None else metadata)


def _open(index: ChromaIndex, existing: dict | None):
    """Run the guard without importing chromadb."""
    client = _FakeClient(existing)
    collection = client.get_or_create_collection(
        name=index.collection_name,
        metadata={
            "hnsw:space": "cosine",
            "embedding_model": index.embedding_model,
            "chunking": index.chunking,
        },
    )
    stored = collection.metadata or {}
    index._check(
        "embedding model", stored.get("embedding_model"), index.embedding_model
    )
    index._check("chunking strategy", stored.get("chunking"), index.chunking)
    return collection


class TestTheCollectionRefusesAMismatch:
    def test_a_different_embedding_model_is_refused(self) -> None:
        index = ChromaIndex(embedding_model="bge-small", chunking="fixed")
        with pytest.raises(RuntimeError, match="embedding model"):
            _open(index, {"embedding_model": "nomic-embed-text", "chunking": "fixed"})

    def test_a_different_chunker_is_refused(self) -> None:
        """C0's chunks and C1's chunks must never share a collection.

        Without this, `index --config C1` on top of a C0 collection leaves a
        mixture, and both configurations then retrieve over the other's chunks.
        Nothing errors and Chapter 4 is quietly contaminated.
        """
        index = ChromaIndex(embedding_model="bge-small", chunking="structure_aware")
        with pytest.raises(RuntimeError, match="chunking strategy"):
            _open(index, {"embedding_model": "bge-small", "chunking": "fixed"})

    def test_a_matching_collection_opens(self) -> None:
        index = ChromaIndex(embedding_model="bge-small", chunking="fixed")
        assert _open(index, {"embedding_model": "bge-small", "chunking": "fixed"})

    def test_a_collection_predating_the_key_is_not_refused(self) -> None:
        """Backwards compatible by design: an older collection recorded no
        chunker, so it cannot be checked. The first rebuild starts the
        protection — stated here so the limitation is not mistaken for cover."""
        index = ChromaIndex(embedding_model="bge-small", chunking="fixed")
        assert _open(index, {"embedding_model": "bge-small"})

    def test_the_error_says_what_to_do(self) -> None:
        index = ChromaIndex(embedding_model="bge-small", chunking="structure_aware")
        with pytest.raises(RuntimeError) as exc:
            _open(index, {"embedding_model": "bge-small", "chunking": "fixed"})
        assert "--reset" in str(exc.value)
        assert "CHROMA_COLLECTION" in str(exc.value)


class TestChunkIdsAreNotStableAcrossRuns:
    """Documents the property the guards above exist to compensate for.

    `Chunk.chunk_id` defaults to a fresh `uuid4`, so re-chunking the same
    document produces different ids for identical text. Two consequences the
    rest of the system has to live with, both asserted here so a future change
    to deterministic ids is a deliberate decision rather than an accident:

    1. Chroma's `upsert` cannot update — the same content indexed twice is
       stored twice, so re-indexing without `--reset` doubles the index.
    2. Dense and sparse indexes only share ids when they were populated in the
       same process from the same chunk objects, which is what makes resetting
       them together mandatory rather than tidy.
    """

    def test_the_same_document_chunks_to_different_ids_each_run(self) -> None:
        document = _document()
        chunker = FixedSizeChunker(size=200, overlap=20)
        first = {chunk.chunk_id for chunk in chunker.chunk(document)}
        second = {chunk.chunk_id for chunk in chunker.chunk(document)}
        assert first.isdisjoint(second)

    def test_content_is_identical_even_though_ids_are_not(self) -> None:
        document = _document()
        chunker = FixedSizeChunker(size=200, overlap=20)
        assert [c.content for c in chunker.chunk(document)] == [
            c.content for c in chunker.chunk(document)
        ]

    def test_the_two_chunkers_do_not_agree_on_chunks(self) -> None:
        """Why one collection cannot hold both C0's and C1's chunks."""
        document = _document()
        fixed = FixedSizeChunker(size=200, overlap=20).chunk(document)
        structured = StructureAwareChunker(max_size=200, overlap=20).chunk(document)
        assert [c.content for c in fixed] != [c.content for c in structured]


class TestTheSparseIndexResets:
    def test_reset_empties_it_and_removes_the_file(self, tmp_path) -> None:
        index = BM25Index(path=str(tmp_path / "bm25.pkl"))
        chunks = FixedSizeChunker(size=200, overlap=20).chunk(_document())
        assert index.add(chunks) == len(chunks)
        assert index.count() == len(chunks)

        index.reset()
        assert index.count() == 0
        assert not (tmp_path / "bm25.pkl").exists()

    def test_reindexing_without_reset_accumulates(self, tmp_path) -> None:
        """The reason `--reset` must reset both indexes, made concrete.

        Re-chunking yields new ids, so BM25's upsert-by-id path never matches
        and the same content is stored twice. A sparse index left unreset
        beside a rebuilt dense index therefore holds stale entries whose ids
        exist nowhere in Chroma — and RRF, which fuses by chunk_id, can never
        pair them with a dense hit.
        """
        index = BM25Index(path=str(tmp_path / "bm25.pkl"))
        document = _document()
        chunker = FixedSizeChunker(size=200, overlap=20)

        first = chunker.chunk(document)
        index.add(first)
        index.add(chunker.chunk(document))

        assert index.count() == len(first) * 2

    def test_reset_then_add_leaves_only_the_new_chunks(self, tmp_path) -> None:
        index = BM25Index(path=str(tmp_path / "bm25.pkl"))
        document = _document()
        chunker = FixedSizeChunker(size=200, overlap=20)

        index.add(chunker.chunk(document))
        index.reset()
        fresh = chunker.chunk(document)
        index.add(fresh)

        assert index.count() == len(fresh)
        found = index.search("alpha beta", top_k=50)
        assert {hit.chunk_id for hit in found} <= {chunk.chunk_id for chunk in fresh}
