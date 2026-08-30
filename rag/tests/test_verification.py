"""Phase 6: C5's post-answer verification.

No Ollama, no Chroma, no torch. `ClaimVerifier` takes a `Generator`, so a
scripted double supplies verdicts and every decision the pipeline makes from
them is asserted directly.

Two areas get disproportionate attention, both because a mistake there is
silent rather than loud:

* **Sentence splitting.** This corpus is full of "Dr.", "B.E.", "M.Tech." and
  "Ph.D.". A naive split leaves fragments, a fragment is trivially unsupported,
  and the hallucination rate goes *up* without anything erroring.
* **The refusal rule.** C5 is the only configuration that can replace a
  generated answer. A refusal fired on a misread verdict destroys good output,
  so the tests pin exactly when it fires and, more importantly, when it does
  not.
"""

from __future__ import annotations

import pytest

from rag.generation.base import GenerationResult
from rag.generation.prompts import REFUSAL_TEXT, assemble_context
from rag.indexing.base import IndexedHit
from rag.verification.base import VerificationResult, Verdict
from rag.verification.claim_check import (
    VERIFY_SYSTEM,
    ClaimVerifier,
    build_verify_prompt,
    parse_verdict,
    split_sentences,
)

# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


def _hit(
    chunk_id: str = "a", content: str = "The intake is 120 students."
) -> IndexedHit:
    return IndexedHit(
        chunk_id=chunk_id,
        content=content,
        score=1.0,
        metadata={"document_id": "d", "document_title": "Prospectus"},
    )


def _context(*hits: IndexedHit):
    return assemble_context(list(hits) or [_hit()])


class _ScriptedGenerator:
    """Returns prepared verdicts and records what it was asked."""

    model_name = "scripted"

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, str | None]] = []

    def generate(self, prompt: str, system: str | None = None) -> GenerationResult:
        self.calls.append((prompt, system))
        index = min(len(self.calls) - 1, len(self.replies) - 1)
        reply = self.replies[index] if self.replies else "SUPPORTED"
        return GenerationResult(
            answer=reply, model_name=self.model_name, latency_ms=1.0
        )


# ---------------------------------------------------------------------------


class TestSplittingSentences:
    """Get this wrong and the hallucination rate rises without an error."""

    def test_plain_sentences_split_on_terminators(self) -> None:
        assert split_sentences("One fact. Two facts! Three? Yes.") == [
            "One fact.",
            "Two facts!",
            "Three?",
            "Yes.",
        ]

    @pytest.mark.parametrize(
        "text",
        [
            "Dr. Sowmya P. teaches here.",
            "The M.E. programme is accredited.",
            "Ph.D. admission follows state rules.",
            "The B.Tech. intake is fixed by the CET Cell.",
        ],
    )
    def test_academic_abbreviations_do_not_split(self, text: str) -> None:
        """Every one of these appears in the PCE corpus."""
        assert split_sentences(text) == [text]

    @pytest.mark.parametrize(
        "text",
        [
            "Dr. Sowmya P. teaches here.",
            "Suhas J. Lawand is a faculty member.",
            "K. Charumathi holds a Ph.D.",
        ],
    )
    def test_single_letter_initials_do_not_split(self, text: str) -> None:
        """Faculty names dominate this corpus, and every one carries initials."""
        assert split_sentences(text) == [text]

    def test_a_known_limitation_a_sentence_ending_in_one_letter_merges(self) -> None:
        """Recorded rather than hidden, because it is a deliberate trade-off.

        Treating a single letter before a full stop as an initial means a real
        sentence ending in one is joined to the next. The verifier then judges
        one longer sentence — a mild loss — whereas the opposite error would
        split a name and manufacture a false hallucination.
        """
        assert split_sentences("It has NAAC grade A. The intake is 120.") == [
            "It has NAAC grade A. The intake is 120."
        ]

    def test_citation_markers_are_kept_with_their_sentence(self) -> None:
        text = "The intake is 120 [S1]. Fees are set by the state [S2]."
        assert split_sentences(text) == [
            "The intake is 120 [S1].",
            "Fees are set by the state [S2].",
        ]

    def test_a_bare_marker_is_not_a_sentence(self) -> None:
        """Otherwise a stray '[S3].' becomes a sentence with no claim, which a
        verifier can only call unsupported."""
        assert split_sentences("A real claim [S1]. [S3].") == ["A real claim [S1]."]

    @pytest.mark.parametrize("text", ["", "   ", "\n\n", "...", "[S1]"])
    def test_nothing_to_split_yields_nothing(self, text: str) -> None:
        assert split_sentences(text) == []


class TestParsingTheVerdict:
    @pytest.mark.parametrize(
        "text",
        [
            "SUPPORTED",
            "supported",
            "**SUPPORTED**",
            "Verdict: SUPPORTED",
            "ALL SUPPORTED",
        ],
    )
    def test_supported_is_recognised_through_its_wrappers(self, text: str) -> None:
        assert parse_verdict(text, 3) == ([], True)

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("UNSUPPORTED: 2", [2]),
            ("UNSUPPORTED: 1, 3", [1, 3]),
            ("unsupported: 2,3", [2, 3]),
            ("**UNSUPPORTED:** 1 and 2", [1, 2]),
            ("UNSUPPORTED 3", [3]),
            ("Answer: UNSUPPORTED: 2, 2, 3", [2, 3]),
        ],
    )
    def test_unsupported_numbers_are_read(self, text: str, expected: list[int]) -> None:
        assert parse_verdict(text, 3) == (expected, True)

    @pytest.mark.parametrize("text", ["UNSUPPORTED: none", "UNSUPPORTED:", "NONE"])
    def test_an_empty_complaint_means_supported(self, text: str) -> None:
        assert parse_verdict(text, 3) == ([], True)

    def test_out_of_range_numbers_are_dropped_not_fatal(self) -> None:
        """A miscount is not a refusal to answer.

        The sentences the verifier did identify remain usable, and dropping the
        impossible one is safer than failing the whole verdict.
        """
        assert parse_verdict("UNSUPPORTED: 2, 9", 3) == ([2], True)

    def test_numbers_that_all_miss_yield_nothing_rather_than_a_refusal(self) -> None:
        """The conservative reading, and it matters.

        With `sentence_count` of 2, "UNSUPPORTED: 7, 8" points at nothing. If
        that were read as "all sentences unsupported" the refusal rule would
        fire and destroy the answer on the strength of two numbers that index
        no sentence at all.
        """
        assert parse_verdict("UNSUPPORTED: 7, 8", 2) == ([], True)

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "   ",
            "I think the answer is mostly fine but hard to say.",
            "The context partially covers this topic.",
        ],
    )
    def test_unreadable_output_is_recorded_not_guessed(self, text: str) -> None:
        assert parse_verdict(text, 3) == ([], False)


class TestTheVerifier:
    def test_a_supported_answer_passes_through(self) -> None:
        result = ClaimVerifier(_ScriptedGenerator("SUPPORTED")).verify(
            "q", "The intake is 120 [S1].", _context()
        )
        assert result.verdict is Verdict.SUPPORTED
        assert result.refused is False
        assert result.support_rate == 1.0

    def test_some_unsupported_sentences_are_named_not_removed(self) -> None:
        answer = "The intake is 120 [S1]. The fee is 90,000 rupees [S1]."
        result = ClaimVerifier(_ScriptedGenerator("UNSUPPORTED: 2")).verify(
            "q", answer, _context()
        )
        assert result.verdict is Verdict.PARTIALLY_SUPPORTED
        assert result.unsupported == [2]
        assert result.unsupported_text == ["The fee is 90,000 rupees [S1]."]
        assert result.refused is False
        assert result.support_rate == 0.5

    def test_every_sentence_unsupported_triggers_the_refusal(self) -> None:
        answer = "The intake is 500 [S1]. The fee is 90,000 rupees [S1]."
        result = ClaimVerifier(_ScriptedGenerator("UNSUPPORTED: 1, 2")).verify(
            "q", answer, _context()
        )
        assert result.verdict is Verdict.UNSUPPORTED
        assert result.refused is True
        assert result.support_rate == 0.0
        # The withheld text is kept, so a refusal can be audited rather than
        # taken on trust.
        assert result.original_answer == answer

    def test_an_unreadable_verdict_never_refuses(self) -> None:
        """The rule C4 established: a parse failure must not change an outcome.

        Refusing here would let a broken verifier delete good answers and
        report the generator as hallucinating.
        """
        result = ClaimVerifier(_ScriptedGenerator("Hard to say, honestly.")).verify(
            "q", "The intake is 120 [S1].", _context()
        )
        assert result.verdict is Verdict.UNPARSEABLE
        assert result.refused is False
        assert result.checked == 0
        assert result.support_rate is None

    def test_empty_context_is_skipped_without_an_llm_call(self) -> None:
        """The 'no information' answer has nothing to verify against.

        Checking it would spend a CPU-minute to conclude that an answer about
        the absence of context is unsupported by the absent context — and then
        refuse it.
        """
        generator = _ScriptedGenerator("UNSUPPORTED: 1")
        result = ClaimVerifier(generator).verify(
            "q", "I have no information on this.", assemble_context([])
        )
        assert result.verdict is Verdict.SKIPPED
        assert result.refused is False
        assert generator.calls == []

    def test_the_prompt_numbers_the_sentences_and_shows_the_context(self) -> None:
        answer = "The intake is 120 [S1]. Fees follow state rules [S1]."
        system, prompt = build_verify_prompt("q", split_sentences(answer), _context())
        assert "EXACTLY ONE line" in system
        assert "  1. The intake is 120 [S1]." in prompt
        assert "  2. Fees follow state rules [S1]." in prompt
        assert "The intake is 120 students." in prompt
        assert system == VERIFY_SYSTEM


class TestTheResultRecord:
    def test_support_rate_is_none_when_nothing_was_checked(self) -> None:
        """Not 1.0. A skipped check is not a perfect score, and averaging it in
        as one would report a system as fully grounded exactly when it was
        never examined."""
        assert VerificationResult().support_rate is None

    def test_the_log_shape_carries_what_chapter_four_needs(self) -> None:
        result = VerificationResult(
            verdict=Verdict.PARTIALLY_SUPPORTED,
            sentences=4,
            checked=4,
            unsupported=[2, 3],
            raw="UNSUPPORTED: 2, 3",
            latency_ms=1234.5,
        )
        log = result.to_log()
        assert log["verdict"] == "partially_supported"
        assert log["supported"] == 2
        assert log["support_rate"] == 0.5
        assert log["refused"] is False
        assert log["latency_ms"] == 1234.5

    def test_skipped_and_unsupported_are_distinguishable(self) -> None:
        """An answer nobody could check and an answer found baseless are
        different results; collapsing them would let a broken verifier look
        like a hallucinating generator."""
        assert Verdict.SKIPPED.value != Verdict.UNSUPPORTED.value
        assert Verdict.UNPARSEABLE.value != Verdict.UNSUPPORTED.value


class TestWhatTheReaderSees:
    """The refusal has to be auditable, or C5 is unfalsifiable."""

    def test_a_refusal_shows_what_was_withheld(self) -> None:
        from rag.pipeline import Answer

        answer = Answer(
            question="q",
            answer=REFUSAL_TEXT,
            config_name="C5",
            model_name="m",
            verification=VerificationResult(
                verdict=Verdict.UNSUPPORTED,
                sentences=1,
                checked=1,
                unsupported=[1],
                refused=True,
                original_answer="The intake is 500 students [S1].",
            ),
        )
        rendered = answer.format()
        assert "withheld" in rendered
        assert "The intake is 500 students [S1]." in rendered

    def test_partial_support_is_reported_with_the_rate(self) -> None:
        from rag.pipeline import Answer

        answer = Answer(
            question="q",
            answer="text",
            config_name="C5",
            model_name="m",
            verification=VerificationResult(
                verdict=Verdict.PARTIALLY_SUPPORTED,
                sentences=4,
                checked=4,
                unsupported=[2],
            ),
        )
        rendered = answer.format()
        assert "sentence(s) 2 of 4" in rendered
        assert "75% supported" in rendered

    def test_earlier_configurations_say_nothing(self) -> None:
        from rag.pipeline import Answer

        answer = Answer(question="q", answer="text", config_name="C4", model_name="m")
        assert "VERIFICATION" not in answer.format()
        assert answer.to_log()["verification"] is None
