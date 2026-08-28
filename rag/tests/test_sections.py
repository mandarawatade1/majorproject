"""Structure-aware chunking depends entirely on this tree being right."""

from rag.ingestion.parsers.sections import sections_from_markdown


class TestHierarchy:
    def test_nesting_produces_breadcrumbs(self) -> None:
        markdown = (
            "# Academics\nIntro.\n\n"
            "## B.Tech\nProgrammes.\n\n"
            "### Computer Engineering\nIntake is 180.\n\n"
            "## M.Tech\nPostgraduate.\n"
        )
        sections = sections_from_markdown(markdown, root_title="Academics")
        paths = [s.section_path for s in sections]

        assert "Academics > B.Tech > Computer Engineering" in paths
        # M.Tech is a sibling of B.Tech, not a child of Computer Engineering.
        assert "Academics > M.Tech" in paths

    def test_parent_indices_point_at_real_parents(self) -> None:
        markdown = "# A\nx\n\n## B\ny\n\n### C\nz\n"
        sections = sections_from_markdown(markdown)
        by_heading = {s.heading: s for s in sections}

        assert by_heading["A"].parent_index is None
        assert sections[by_heading["B"].parent_index].heading == "A"
        assert sections[by_heading["C"].parent_index].heading == "B"

    def test_returning_to_a_shallower_level_closes_deeper_ones(self) -> None:
        markdown = "# A\n1\n\n### D\n2\n\n## B\n3\n"
        sections = sections_from_markdown(markdown)
        b = next(s for s in sections if s.heading == "B")
        assert sections[b.parent_index].heading == "A"


class TestContentPreservation:
    def test_preamble_before_the_first_heading_is_kept(self) -> None:
        markdown = "Text with no heading above it.\n\n# First\nBody.\n"
        sections = sections_from_markdown(markdown, root_title="Doc")
        assert any("no heading above it" in s.content for s in sections)

    def test_document_without_headings_still_yields_a_section(self) -> None:
        sections = sections_from_markdown("Just a paragraph.", root_title="Doc")
        assert len(sections) == 1
        assert sections[0].content == "Just a paragraph."

    def test_empty_input_yields_nothing(self) -> None:
        assert sections_from_markdown("") == []

    def test_hash_inside_a_code_fence_is_not_a_heading(self) -> None:
        markdown = "# Real\nbody\n\n```\n# not a heading\n```\n\n## Also real\nmore\n"
        headings = [s.heading for s in sections_from_markdown(markdown)]
        assert "not a heading" not in headings
        assert {"Real", "Also real"} <= set(headings)


class TestSubstantive:
    def test_heading_with_no_body_is_not_substantive(self) -> None:
        sections = sections_from_markdown("# Empty\n\n## Also empty\n")
        assert all(not s.is_substantive for s in sections)

    def test_heading_with_real_body_is_substantive(self) -> None:
        sections = sections_from_markdown("# Full\n" + "content " * 30)
        assert sections[0].is_substantive

    def test_order_index_is_sequential(self) -> None:
        sections = sections_from_markdown("# A\n1\n\n# B\n2\n\n# C\n3\n")
        assert [s.order_index for s in sections] == list(range(len(sections)))
