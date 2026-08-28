"""The demo loader is the single gate that guarantees synthetic data is
labelled. Every rejection path here is load-bearing: if any of these were to
pass silently, unlabelled synthetic content could reach a citation."""

from pathlib import Path

import pytest

from rag.ingestion.parsers.markdown import (
    DemoFrontMatterError,
    load_demo_corpus,
    parse_demo_markdown,
)

VALID = """---
title: "Test circular"
doc_id: "DEMO/TEST/2026/01"
is_demo: true
demo_reason: "Internal circulars are not published publicly anywhere."
category: "circular"
department: "Computer Engineering"
created: "2026-08-28"
---

## Section one

Body text that is long enough to be meaningful.
"""


def _write(tmp_path: Path, content: str, name: str = "doc.md") -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


class TestAcceptance:
    def test_valid_document_loads(self, tmp_path: Path) -> None:
        document = parse_demo_markdown(_write(tmp_path, VALID))
        assert document.is_demo is True
        assert document.doc_id == "DEMO/TEST/2026/01"
        assert document.department == "Computer Engineering"
        assert document.demo_reason

    def test_sections_are_built(self, tmp_path: Path) -> None:
        document = parse_demo_markdown(_write(tmp_path, VALID))
        assert any(s.heading == "Section one" for s in document.sections)

    def test_a_valid_demo_document_also_passes_model_validation(self, tmp_path: Path) -> None:
        assert parse_demo_markdown(_write(tmp_path, VALID)).validate() == []


class TestRejection:
    def test_no_front_matter_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(DemoFrontMatterError, match="no YAML front matter"):
            parse_demo_markdown(_write(tmp_path, "# Just a heading\n\nBody."))

    def test_unclosed_front_matter_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(DemoFrontMatterError, match="not closed"):
            parse_demo_markdown(_write(tmp_path, "---\ntitle: x\n\nBody."))

    @pytest.mark.parametrize("key", ["title", "doc_id", "is_demo", "demo_reason", "category"])
    def test_each_required_key_is_enforced(self, tmp_path: Path, key: str) -> None:
        content = "\n".join(line for line in VALID.splitlines() if not line.startswith(f"{key}:"))
        with pytest.raises(DemoFrontMatterError, match="missing required key"):
            parse_demo_markdown(_write(tmp_path, content))

    def test_is_demo_false_is_rejected(self, tmp_path: Path) -> None:
        """A file under corpus/demo/ is synthetic by definition."""
        with pytest.raises(DemoFrontMatterError, match="must be literally true"):
            parse_demo_markdown(_write(tmp_path, VALID.replace("is_demo: true", "is_demo: false")))

    def test_a_perfunctory_demo_reason_is_rejected(self, tmp_path: Path) -> None:
        content = VALID.replace(
            'demo_reason: "Internal circulars are not published publicly anywhere."',
            'demo_reason: "fake"',
        )
        with pytest.raises(DemoFrontMatterError, match="at least 20 characters"):
            parse_demo_markdown(_write(tmp_path, content))

    def test_unknown_category_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(DemoFrontMatterError, match="unknown category"):
            parse_demo_markdown(_write(tmp_path, VALID.replace('"circular"', '"nonsense"')))

    def test_empty_body_is_rejected(self, tmp_path: Path) -> None:
        head = VALID.split("---")[1]
        with pytest.raises(DemoFrontMatterError, match="body is empty"):
            parse_demo_markdown(_write(tmp_path, f"---{head}---\n\n   \n"))


class TestCorpusLoading:
    def test_errors_are_collected_not_raised(self, tmp_path: Path) -> None:
        """One malformed file must not abort ingestion of the rest."""
        _write(tmp_path, VALID, "good.md")
        _write(tmp_path, "# no front matter", "bad.md")

        documents, errors = load_demo_corpus(tmp_path)
        assert len(documents) == 1
        assert len(errors) == 1
        assert "bad.md" in errors[0]

    def test_readme_is_not_treated_as_a_document(self, tmp_path: Path) -> None:
        _write(tmp_path, "# Demo corpus\n\nExplanatory text.", "README.md")
        documents, errors = load_demo_corpus(tmp_path)
        assert documents == []
        assert errors == []
